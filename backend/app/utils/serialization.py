"""JSON encoding helper.

Lives in utils rather than in `main` so route modules can use it without
importing the application factory, which would be a circular import.
"""

from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder


def jsonable(value: Any) -> Any:
    return jsonable_encoder(value)
