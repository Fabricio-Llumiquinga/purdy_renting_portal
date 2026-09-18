"""Shared validation and formatting utilities for the Purdy Renting platform.

This module centralizes input validation, business-rule constants, and the
Costa Rican date-formatting convention so that all Lambda handlers apply the
same rules consistently.

Requirements covered: 2.8, 3.5, 7.5, 10.4, 9.3
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

#: File extensions accepted for user uploads (lowercase, dot-prefixed).
ALLOWED_EXTENSIONS: set[str] = {".xls", ".xlsx", ".csv"}

#: Maximum allowed size for user-uploaded files (10 MB).
MAX_USER_FILE_SIZE: int = 10 * 1024 * 1024

#: Maximum allowed size for Robot-generated files (50 MB).
MAX_GENERATED_FILE_SIZE: int = 50 * 1024 * 1024

#: Mapping of valid company display names to their short codes.
VALID_COMPANIES: dict[str, str] = {"Purdy Motor": "PM", "Automotriz": "AUTO"}

#: Status values the Robot may report via the update-status endpoint.
VALID_STATUSES: set[str] = {"Procesando", "Procesado", "Failed"}

#: Statuses that are terminal (no further transitions allowed).
TERMINAL_STATUSES: set[str] = {"Procesado", "Failed"}

# --- Endpoint de resultado (POST /requests/{id}/result) -------------------- #
#: Valores de "status" que el Robot envia al cerrar la solicitud, y su mapeo al
#: estado interno usado por el frontend/seguimiento.
RESULT_STATUS_MAP: dict[str, str] = {
    "Success": "Procesado",
    "Failed": "Failed",
}

#: Valores permitidos de "type_failed" que el Robot puede reportar.
VALID_FAILURE_TYPES: set[str] = {"Business Exception", "IT Exception", ""}

#: Longitud maxima del campo "detail" del resultado.
MAX_DETAIL_LENGTH: int = 1000

#: Maximum length of the Robot observation field.
MAX_OBSERVATION_LENGTH: int = 500

#: Maximum length for generic text fields.
MAX_TEXT_FIELD_LENGTH: int = 1000

#: Initial status assigned to newly created requests.
INITIAL_STATUS: str = "Pendiente de Procesar"

#: Allowed status transitions expressed as {current_status: {allowed_next, ...}}.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "Pendiente de Procesar": {"Procesando", "Failed"},
    "Procesando": {"Procesado", "Failed"},
}

#: Costa Rican display format for dates: dd/MM/yyyy HH:mm.
DATE_FORMAT_CR: str = "%d/%m/%Y %H:%M"

# Patterns used by sanitize_input to detect dangerous content.
_SCRIPT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"<\s*/\s*script", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"vbscript\s*:", re.IGNORECASE),
    re.compile(r"data\s*:\s*text/html", re.IGNORECASE),
    # Inline event handlers such as onerror=, onclick=, onload=, etc.
    re.compile(r"\bon[a-z]+\s*=", re.IGNORECASE),
)


# --------------------------------------------------------------------------- #
# Validators
# --------------------------------------------------------------------------- #


def validate_file_extension(filename: str) -> bool:
    """Return True if *filename* ends with an allowed extension.

    The check is case-insensitive and matches Property 1: a filename is
    accepted if and only if it ends with one of ``.xls``, ``.xlsx`` or
    ``.csv``.

    Requirements: 2.8, 3.5
    """
    if not isinstance(filename, str) or not filename:
        return False
    lowered = filename.lower()
    return any(lowered.endswith(ext) for ext in ALLOWED_EXTENSIONS)


def validate_company(company: str) -> tuple[bool, str | None]:
    """Validate a company name and return ``(is_valid, company_code)``.

    Returns ``(True, code)`` for a recognized company, otherwise
    ``(False, None)``. Matches Property 2.

    Requirements: 2.8 (input validation)
    """
    if not isinstance(company, str):
        return (False, None)
    code = VALID_COMPANIES.get(company)
    if code is None:
        return (False, None)
    return (True, code)


def validate_status_transition(current_status: str, new_status: str) -> bool:
    """Return True only for allowed status-machine transitions.

    Allowed transitions (Property 3):
      - "Pendiente de Procesar" -> "Procesando" or "Failed"
      - "Procesando"            -> "Procesado" or "Failed"
    All other transitions are rejected, including any transition out of a
    terminal status.

    Requirements: 7.5
    """
    if not isinstance(current_status, str) or not isinstance(new_status, str):
        return False
    allowed = _ALLOWED_TRANSITIONS.get(current_status)
    if allowed is None:
        return False
    return new_status in allowed


def sanitize_input(value: str, max_length: int = MAX_TEXT_FIELD_LENGTH) -> str:
    """Validate and return a safe text value.

    Raises ``ValueError`` when the input:
      - is not a string,
      - exceeds *max_length*,
      - contains control characters (other than the tab/newline pair used in
        normal multi-line text is still rejected here, as control characters
        are disallowed for these fields), or
      - contains script/HTML-event content.

    Safe input is returned unchanged. This matches Property 5 and Requirement
    10.4, which requires rejecting parameters containing unescaped control
    characters or script content.

    Requirements: 10.4
    """
    if not isinstance(value, str):
        raise ValueError("El valor debe ser una cadena de texto.")

    if len(value) > max_length:
        raise ValueError(
            f"El valor excede la longitud máxima de {max_length} caracteres."
        )

    # Reject control characters (Unicode category "Cc") such as NUL, ESC, or
    # other non-printable bytes. These have no legitimate place in the text
    # fields validated here.
    for char in value:
        if unicodedata.category(char) == "Cc":
            raise ValueError("El valor contiene caracteres de control no permitidos.")

    # Reject known script / injection patterns.
    for pattern in _SCRIPT_PATTERNS:
        if pattern.search(value):
            raise ValueError("El valor contiene contenido no permitido.")

    return value


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #


def format_date_cr(dt: datetime) -> str:
    """Format *dt* as ``dd/MM/yyyy HH:mm`` for Costa Rican display.

    Matches Property 4: parsing the returned string back with the same format
    yields a datetime equivalent to the original truncated to minutes.

    Requirements: 9.3
    """
    if not isinstance(dt, datetime):
        raise ValueError("Se requiere un objeto datetime válido.")
    return dt.strftime(DATE_FORMAT_CR)
