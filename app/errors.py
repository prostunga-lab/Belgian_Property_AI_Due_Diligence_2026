"""Errors whose message is a catalog key, translated when the response is built (UI language or API Accept-Language)."""
from __future__ import annotations

from fastapi import HTTPException


class AppError(HTTPException):
    def __init__(self, status_code: int, key: str, **params):
        super().__init__(status_code=status_code, detail=key)
        self.key = key
        self.params = params
