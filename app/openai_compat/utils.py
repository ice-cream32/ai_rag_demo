"""Utilities for OpenAI-compatible layer."""

import uuid
from typing import Optional
from fastapi import Request
from fastapi.responses import JSONResponse


def openai_error(status_code: int, message: str, error_type: str, code: str, param: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": message,
                "type": error_type,
                "param": param,
                "code": code,
            }
        },
    )


def get_request_id(request: Request) -> str:
    rid = request.headers.get("X-Request-Id", "").strip()
    return rid or f"req_{uuid.uuid4().hex[:16]}"


def _extract_bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return ""
    return authorization[len(prefix):].strip()


def resolve_auth_key(request: Request) -> tuple[str, str]:
    """Return (auth_key, auth_source). auth_source in {bearer, x-api-key, none}."""
    bearer = _extract_bearer_token(request.headers.get("Authorization", ""))
    if bearer:
        return bearer, "bearer"
    x_api_key = request.headers.get("X-API-Key", "")
    if x_api_key:
        return x_api_key, "x-api-key"
    return "", "none"


def authenticate_openai_request(request: Request, expected_api_key: str) -> tuple[bool, str, str, Optional[JSONResponse]]:
    """
    Unified auth dependency-style helper.

    Returns:
      (ok, request_id, auth_source, error_response)
    """
    request_id = get_request_id(request)
    if not expected_api_key:
        return True, request_id, "none", None

    auth_key, auth_source = resolve_auth_key(request)
    if auth_key == expected_api_key:
        return True, request_id, auth_source, None

    return (
        False,
        request_id,
        auth_source,
        openai_error(
            status_code=401,
            message="Invalid authentication credentials",
            error_type="invalid_request_error",
            code="invalid_api_key",
        ),
    )


def ensure_openai_compat_auth(request: Request, api_key: str) -> Optional[JSONResponse]:
    """
    Minimal auth compatibility skeleton:
    - If api_key is empty: allow.
    - Accept either Authorization: Bearer <token> or X-API-Key.
    """
    ok, _, _, err = authenticate_openai_request(request, api_key)
    if ok:
        return None
    return err
