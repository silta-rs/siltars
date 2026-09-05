import unittest

from silta import Route, App, EXECUTION_PLAN_VERSION, ExecutionMode, OperationKind


class AppRouteValidationTests(unittest.TestCase):
    def test_describes_versioned_execution_plan(self) -> None:
        app = App(name="planned")

        plan = app.describe()

        self.assertEqual(plan["plan_version"], EXECUTION_PLAN_VERSION)
        self.assertEqual(plan["name"], "planned")

    def test_rejects_unclosed_route_parameter(self) -> None:
        app = App()

        with self.assertRaisesRegex(ValueError, "complete path segments"):
            app.get("/a/{unclosed")

    def test_accepts_complete_route_parameter(self) -> None:
        app = App()

        @app.get("/a/{item_id}")
        def handler() -> dict[str, bool]:
            return {"ok": True}

        self.assertEqual(app.routes[0].path, "/a/{item_id}")

    def test_rejects_non_ascii_route_parameter(self) -> None:
        app = App()

        with self.assertRaisesRegex(ValueError, "valid identifiers"):
            app.get("/a/{ид}")

    def test_describes_python_handler_route(self) -> None:
        app = App()

        @app.post("/python/echo", python=True)
        def echo() -> dict[str, bool]:
            return {"ok": True}

        route = app.describe()["routes"][0]
        self.assertEqual(route["method"], "POST")
        self.assertEqual(route["path"], "/python/echo")
        self.assertTrue(route["handler"].endswith("echo"))
        self.assertTrue(route["python_handler"])
        self.assertEqual(route["execution"]["mode"], "hybrid")
        self.assertEqual(route["execution"]["operation"], "python_handler")
        self.assertEqual(route["execution"]["reason"], "explicit_python_handler")

    def test_ordinary_handler_automatically_uses_hybrid_execution(self) -> None:
        app = App()

        @app.post("/echo")
        async def echo() -> dict[str, bool]:
            return {"ok": True}

        route = app.routes[0]
        description = app.describe()["routes"][0]

        self.assertEqual(route.execution.mode, ExecutionMode.HYBRID)
        self.assertEqual(route.execution.operation, OperationKind.PYTHON_HANDLER)
        self.assertEqual(description["execution"]["reason"], "automatic_python_handler")
        self.assertTrue(description["python_handler"])

    def test_static_response_automatically_uses_native_execution(self) -> None:
        app = App()

        @app.get("/health", response={"ok": True})
        async def health() -> dict[str, bool]:
            return {"ok": True}

        route = app.describe()["routes"][0]

        self.assertEqual(route["execution"]["mode"], "native")
        self.assertEqual(route["execution"]["operation"], "static_response")
        self.assertNotIn("python_handler", route)

    def test_explicit_false_preserves_pre_alpha_native_handler(self) -> None:
        app = App()

        @app.get("/rates", python=False)
        def rates() -> dict[str, list[object]]:
            return {"rates": []}

        route = app.describe()["routes"][0]

        self.assertEqual(route["execution"]["mode"], "native")
        self.assertEqual(route["execution"]["operation"], "legacy_symbolic")
        self.assertEqual(
            route["execution"]["reason"], "explicit_legacy_native_handler"
        )
        self.assertNotIn("python_handler", route)

    def test_rejects_python_handler_with_native_response(self) -> None:
        app = App()

        with self.assertRaisesRegex(ValueError, "python routes"):
            app.get("/hello", response={"hello": "world"}, python=True)

    def test_direct_route_constructor_remains_compatible(self):
        def handler():
            return {"ok": True}
        route = Route("GET", "/ok", handler, python_handler=True)
        self.assertTrue(route.python_handler)
        self.assertEqual(route.execution.mode, ExecutionMode.HYBRID)
        legacy = Route("GET", "/ok", handler)
        self.assertFalse(legacy.python_handler)
        self.assertEqual(legacy.execution.operation, OperationKind.LEGACY_SYMBOLIC)

    def test_route_declaration_does_not_execute_handler(self):
        def handler():
            raise AssertionError("must not run during plan generation")
        app = App()
        app.get("/unsafe")(handler)
        self.assertEqual(app.describe()["routes"][0]["execution"]["mode"], "hybrid")

    def test_invalid_static_json_is_rejected_at_declaration(self):
        for body in ({"bad": float("nan")}, {"bad": set()}):
            with self.subTest(body=body), self.assertRaises((TypeError, ValueError)):
                App().get("/bad", response=body)


if __name__ == "__main__":
    unittest.main()
