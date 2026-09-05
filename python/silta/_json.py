"""JSON values that cross Silta's Python/Serde boundary without coercion."""
from __future__ import annotations

import math
from typing import Any


def validate_json(value: Any) -> None:
    """Reject values Serde cannot represent faithfully, including object keys."""
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 64:
            raise ValueError("JSON exceeds maximum depth of 64")
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise TypeError("JSON object keys must be strings")
                key.encode("utf-8")
                pending.append((child, depth + 1))
        elif isinstance(item, (list, tuple)):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, str):
            item.encode("utf-8")
        elif item is None or isinstance(item, bool):
            continue
        elif isinstance(item, int):
            if not -(2**63) <= item < 2**64:
                raise ValueError("integer exceeds the Serde JSON signed/unsigned 64-bit range")
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("JSON numbers must be finite")
        else:
            raise TypeError(f"unsupported JSON type: {type(item).__name__}")
