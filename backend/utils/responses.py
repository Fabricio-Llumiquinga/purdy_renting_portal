"""Shared response and error utilities for the Purdy Renting platform.

Provides helper functions that build consistent API Gateway-style responses
(Lambda proxy integration). Success and error responses share a common shape:
they include an HTTP ``statusCode``, CORS-enabled ``headers`` and a JSON-encoded
``body``.

Error responses follow the structure defined in the design document:

    {
        "error": {
            "code": "ERROR_CODE",
            "message": "Mensaje en español"
        }
    }

All user-facing error messages are in Spanish (Requirement 9.1, 9.2).
"""

import json
from enum import Enum
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# CORS headers
# ---------------------------------------------------------------------------
# CORS is configured to allow cross-origin requests from the frontend. The
# origin is left as "*" here for the Lambda-level default; API Gateway / the
# infrastructure template can further restrict this to the frontend domain.
CORS_HEADERS: Dict[str, str] = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Api-Key",
    "Access-Control-Allow-Methods": "GET,POST,PUT,OPTIONS",
}


# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------
class ErrorCode(str, Enum):
    """Canonical error codes matching the design document error table.

    Inheriting from ``str`` lets each member serialize directly to its string
    value in JSON payloads (e.g. ``ErrorCode.INVALID_FILE_FORMAT`` -> the
    string ``"INVALID_FILE_FORMAT"``).
    """

    INVALID_FILE_FORMAT = "INVALID_FILE_FORMAT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_COMPANY = "INVALID_COMPANY"
    INVALID_STATUS = "INVALID_STATUS"
    INVALID_BASE64 = "INVALID_BASE64"
    OBSERVATION_TOO_LONG = "OBSERVATION_TOO_LONG"
    INVALID_INPUT = "INVALID_INPUT"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    REQUEST_NOT_FOUND = "REQUEST_NOT_FOUND"
    REQUEST_TERMINAL_STATE = "REQUEST_TERMINAL_STATE"
    STORAGE_ERROR = "STORAGE_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# HTTP status mapping (per design document error table)
# ---------------------------------------------------------------------------
ERROR_STATUS_MAP: Dict[ErrorCode, int] = {
    ErrorCode.INVALID_FILE_FORMAT: 400,
    ErrorCode.FILE_TOO_LARGE: 400,
    ErrorCode.MISSING_REQUIRED_FIELD: 400,
    ErrorCode.INVALID_COMPANY: 400,
    ErrorCode.INVALID_STATUS: 400,
    ErrorCode.INVALID_BASE64: 400,
    ErrorCode.OBSERVATION_TOO_LONG: 400,
    ErrorCode.INVALID_INPUT: 400,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.REQUEST_NOT_FOUND: 404,
    ErrorCode.REQUEST_TERMINAL_STATE: 409,
    ErrorCode.STORAGE_ERROR: 500,
    ErrorCode.DATABASE_ERROR: 500,
    ErrorCode.INTERNAL_ERROR: 500,
}


# ---------------------------------------------------------------------------
# Default Spanish messages
# ---------------------------------------------------------------------------
ERROR_MESSAGES: Dict[ErrorCode, str] = {
    ErrorCode.INVALID_FILE_FORMAT: (
        "Formato de archivo no válido. Solo se permiten archivos .xls, .xlsx o .csv."
    ),
    ErrorCode.FILE_TOO_LARGE: "El archivo excede el tamaño máximo permitido.",
    ErrorCode.MISSING_REQUIRED_FIELD: "Falta un campo obligatorio.",
    ErrorCode.INVALID_COMPANY: "La empresa seleccionada no es válida.",
    ErrorCode.INVALID_STATUS: "El estado indicado no es válido.",
    ErrorCode.INVALID_BASE64: "El contenido del archivo no es un base64 válido.",
    ErrorCode.OBSERVATION_TOO_LONG: (
        "La observación excede el máximo de 500 caracteres."
    ),
    ErrorCode.INVALID_INPUT: (
        "La entrada contiene caracteres o contenido no permitidos."
    ),
    ErrorCode.UNAUTHORIZED: "No autorizado. El token o la clave de API no son válidos.",
    ErrorCode.FORBIDDEN: "No tiene permiso para acceder a este recurso.",
    ErrorCode.REQUEST_NOT_FOUND: "La solicitud indicada no existe.",
    ErrorCode.REQUEST_TERMINAL_STATE: (
        "La solicitud ya se encuentra en un estado final y no puede modificarse."
    ),
    ErrorCode.STORAGE_ERROR: (
        "Ocurrió un error al procesar el archivo. Intente nuevamente."
    ),
    ErrorCode.DATABASE_ERROR: (
        "Ocurrió un error al guardar la información. Intente nuevamente."
    ),
    ErrorCode.INTERNAL_ERROR: (
        "Ocurrió un error inesperado. Intente nuevamente más tarde."
    ),
}


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------
def build_response(
    status_code: int,
    body: Any,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build a raw API Gateway (Lambda proxy) response.

    Args:
        status_code: HTTP status code for the response.
        body: A JSON-serializable object to encode as the response body.
        extra_headers: Optional additional headers merged over the CORS defaults.

    Returns:
        A dict with ``statusCode``, ``headers`` and a JSON string ``body``.
    """
    headers = dict(CORS_HEADERS)
    if extra_headers:
        headers.update(extra_headers)

    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, ensure_ascii=False),
    }


def success_response(
    body: Any = None,
    status_code: int = 200,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build a successful API Gateway-style response.

    Args:
        body: A JSON-serializable object for the response body. Defaults to an
            empty object.
        status_code: HTTP success status code (default 200).
        extra_headers: Optional additional headers.

    Returns:
        An API Gateway proxy response dict.
    """
    if body is None:
        body = {}
    return build_response(status_code, body, extra_headers)


def error_response(
    code: ErrorCode,
    message: Optional[str] = None,
    status_code: Optional[int] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build an error API Gateway-style response in the standard error shape.

    Args:
        code: The :class:`ErrorCode` describing the error.
        message: Optional Spanish message overriding the default for the code.
        status_code: Optional HTTP status override. Defaults to the mapping in
            :data:`ERROR_STATUS_MAP`.
        extra_headers: Optional additional headers.

    Returns:
        An API Gateway proxy response dict with body::

            {"error": {"code": "...", "message": "Mensaje en español"}}
    """
    if status_code is None:
        status_code = ERROR_STATUS_MAP.get(code, 500)

    if message is None:
        message = ERROR_MESSAGES.get(code, ERROR_MESSAGES[ErrorCode.INTERNAL_ERROR])

    body = {"error": {"code": code.value, "message": message}}
    return build_response(status_code, body, extra_headers)
