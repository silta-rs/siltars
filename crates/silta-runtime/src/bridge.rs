//! One task owns the worker, its IPC stream, and all restart/cleanup decisions.
use std::process::Stdio;
use std::sync::Arc;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};
use tokio::sync::{mpsc, oneshot, watch, Mutex};
use tokio::task::JoinHandle;
use tokio::time::{sleep, sleep_until, Instant};

use super::{io_other, RuntimeError, RuntimeRouteError};

const QUEUE_CAPACITY: usize = 64;
const MIN_BACKOFF: Duration = Duration::from_millis(100);
const STARTUP_TIMEOUT: Duration = Duration::from_secs(10);
const MAX_BACKOFF: Duration = Duration::from_secs(5);
// Bound memory even if a broken worker writes an unterminated protocol frame.
const MAX_RESPONSE_BYTES: u64 = 16 * 1024 * 1024;

type Reply = Result<PythonBridgeResponse, RuntimeRouteError>;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Lifecycle {
    Running,
    Draining,
    Stopping,
}

#[derive(Debug)]
struct Call {
    handler: String,
    body: Value,
    deadline: Instant,
    reply: oneshot::Sender<Reply>,
}

#[derive(Debug, Clone)]
pub(super) struct PythonBridge {
    calls: mpsc::Sender<Call>,
    lifecycle: watch::Sender<Lifecycle>,
    supervisor: Arc<Mutex<Option<JoinHandle<std::io::Result<()>>>>>,
}

#[derive(Debug, Serialize)]
struct PythonBridgeRequest {
    id: u64,
    handler: String,
    body: Value,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct PythonBridgeResponse {
    id: u64,
    pub(super) status: u16,
    pub(super) body: Value,
}

struct Worker {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: u64,
    ready: bool,
}

impl PythonBridge {
    pub(super) async fn spawn(executable: &str, target: &str) -> Result<Self, RuntimeError> {
        let worker = Worker::spawn(executable, target).map_err(RuntimeError::PythonBridge)?;
        let (calls, receiver) = mpsc::channel(QUEUE_CAPACITY);
        let (lifecycle, changes) = watch::channel(Lifecycle::Running);
        let supervisor = tokio::spawn(supervise(
            executable.to_owned(),
            target.to_owned(),
            worker,
            receiver,
            changes,
        ));
        Ok(Self {
            calls,
            lifecycle,
            supervisor: Arc::new(Mutex::new(Some(supervisor))),
        })
    }

    pub(super) fn begin_drain(&self) {
        self.lifecycle.send_replace(Lifecycle::Draining);
    }

    pub(super) async fn shutdown(&self) -> Result<(), RuntimeError> {
        self.lifecycle.send_replace(Lifecycle::Stopping);
        if let Some(task) = self.supervisor.lock().await.take() {
            task.await
                .map_err(|_| RuntimeError::PythonBridge(io_other("worker supervisor failed")))?
                .map_err(RuntimeError::PythonBridge)?;
        }
        Ok(())
    }

    pub(super) async fn call(&self, handler: String, body: Value, deadline: Instant) -> Reply {
        if *self.lifecycle.borrow() != Lifecycle::Running {
            return Err(RuntimeRouteError::PythonBridgeUnavailable);
        }
        let (reply, receiver) = oneshot::channel();
        self.calls
            .try_send(Call {
                handler,
                body,
                deadline,
                reply,
            })
            .map_err(|_| RuntimeRouteError::PythonBridgeUnavailable)?;
        // Dropping this receiver cancels queued work, or kills/reaps an active
        // worker. A partially written request can never contaminate its successor.
        receiver
            .await
            .unwrap_or(Err(RuntimeRouteError::PythonBridgeUnavailable))
    }
}

async fn supervise(
    executable: String,
    target: String,
    initial: Worker,
    mut calls: mpsc::Receiver<Call>,
    mut lifecycle: watch::Receiver<Lifecycle>,
) -> std::io::Result<()> {
    let mut worker = Some(initial);
    let mut backoff = MIN_BACKOFF;
    loop {
        if *lifecycle.borrow() != Lifecycle::Running {
            break;
        }
        if worker.is_none() {
            // Restart even without traffic. Repeated import crashes/spawn failures
            // back off exponentially; only a completed IPC call resets the delay.
            tokio::select! {
                biased;
                changed = lifecycle.changed() => {
                    if changed.is_err() { break; }
                    continue;
                },
                _ = sleep(backoff) => {},
            }
            if *lifecycle.borrow() != Lifecycle::Running {
                break;
            }
            backoff = (backoff * 2).min(MAX_BACKOFF);
            match Worker::spawn(&executable, &target) {
                Ok(next) => worker = Some(next),
                Err(error) => {
                    eprintln!(
                        "silta-runtime: worker restart failed: {error}; retrying with backoff"
                    );
                    continue;
                }
            }
        }
        let current = worker.as_mut().expect("worker spawned");
        if !current.ready {
            let ready = tokio::select! {
                biased;
                changed = lifecycle.changed() => {
                    if changed.is_err() { break; }
                    continue;
                },
                result = tokio::time::timeout(STARTUP_TIMEOUT, current.wait_ready()) => result,
            };
            if !matches!(ready, Ok(Ok(()))) {
                eprintln!("silta-runtime: Python worker failed readiness; restarting");
                current.reap(false).await?;
                worker = None;
                continue;
            }
            current.ready = true;
        }
        let call = tokio::select! {
            biased;
            changed = lifecycle.changed() => {
                if changed.is_err() { break; }
                continue;
            },
            status = current.child.wait() => {
                status?; // Reap idle crashes too, without waiting for HTTP traffic.
                eprintln!("silta-runtime: idle Python worker exited; restarting");
                worker = None;
                continue;
            },
            call = calls.recv() => match call { Some(call) => call, None => break },
        };
        let Call {
            handler,
            body,
            deadline,
            mut reply,
        } = call;
        if reply.is_closed() {
            continue;
        }
        if Instant::now() >= deadline {
            let _ = reply.send(Err(RuntimeRouteError::RequestTimeout));
            continue;
        }
        let result = {
            let exchange = current.exchange(handler, body);
            tokio::pin!(exchange);
            loop {
                tokio::select! {
                    biased;
                    changed = lifecycle.changed() => {
                        if changed.is_err() || *lifecycle.borrow() == Lifecycle::Stopping {
                            break Err(RuntimeRouteError::PythonBridgeUnavailable);
                        }
                        // Draining lets this call finish, but never starts another.
                    },
                    _ = reply.closed() => break Err(RuntimeRouteError::RequestTimeout),
                    _ = sleep_until(deadline) => break Err(RuntimeRouteError::RequestTimeout),
                    result = &mut exchange => break result,
                }
            }
        };
        if result.is_err() {
            // No replay: application side effects may already have happened.
            // EOF uses wait first. All other failures invalidate the entire stream.
            let eof = matches!(result, Err(RuntimeRouteError::PythonBridgeClosed));
            current.reap(eof).await?;
            worker = None;
        } else {
            backoff = MIN_BACKOFF;
        }
        let _ = reply.send(result);
    }
    calls.close();
    if let Some(mut current) = worker {
        current.reap(false).await?;
    }
    // Closing queued reply channels yields 503 without dispatching their handlers.
    Ok(())
}

impl Worker {
    fn spawn(executable: &str, target: &str) -> std::io::Result<Self> {
        let mut child = Command::new(executable)
            .args(["-m", "silta.cli", "_bridge", target, "--ready"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .kill_on_drop(true)
            .spawn()?;
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| io_other("missing stdin"))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| io_other("missing stdout"))?;
        Ok(Self {
            child,
            stdin,
            stdout: BufReader::new(stdout),
            next_id: 1,
            ready: false,
        })
    }

    async fn wait_ready(&mut self) -> std::io::Result<()> {
        let mut line = Vec::new();
        (&mut self.stdout)
            .take(1024)
            .read_until(b'\n', &mut line)
            .await?;
        if line != b"{\"ready\":1}\n" {
            return Err(io_other("invalid worker readiness frame"));
        }
        Ok(())
    }

    async fn reap(&mut self, eof: bool) -> std::io::Result<()> {
        if eof {
            if let Ok(status) =
                tokio::time::timeout(Duration::from_secs(1), self.child.wait()).await
            {
                status?;
                return Ok(());
            }
        }
        // Tokio kill includes wait/reap; the supervisor is never cancelled by
        // an HTTP deadline, disconnect, or the server's graceful drain timeout.
        self.child.kill().await
    }

    async fn exchange(&mut self, handler: String, body: Value) -> Reply {
        let id = self.next_id;
        self.next_id = self.next_id.wrapping_add(1);
        let mut line = serde_json::to_vec(&PythonBridgeRequest { id, handler, body })
            .map_err(RuntimeRouteError::PythonBridgeSerialize)?;
        line.push(b'\n');
        self.stdin
            .write_all(&line)
            .await
            .map_err(RuntimeRouteError::PythonBridgeIo)?;
        self.stdin
            .flush()
            .await
            .map_err(RuntimeRouteError::PythonBridgeIo)?;
        let mut response_line = Vec::new();
        let bytes_read = (&mut self.stdout)
            .take(MAX_RESPONSE_BYTES + 1)
            .read_until(b'\n', &mut response_line)
            .await
            .map_err(RuntimeRouteError::PythonBridgeIo)?;
        if bytes_read == 0 {
            return Err(RuntimeRouteError::PythonBridgeClosed);
        }
        if bytes_read as u64 > MAX_RESPONSE_BYTES || response_line.last() != Some(&b'\n') {
            return Err(RuntimeRouteError::PythonBridgeProtocol(
                "oversized or incomplete response".into(),
            ));
        }
        let response: PythonBridgeResponse = serde_json::from_slice(&response_line)
            .map_err(|error| RuntimeRouteError::PythonBridgeProtocol(error.to_string()))?;
        if response.id != id || !(200..=599).contains(&response.status) {
            return Err(RuntimeRouteError::PythonBridgeProtocol(
                "invalid response id or status".into(),
            ));
        }
        Ok(response)
    }
}
