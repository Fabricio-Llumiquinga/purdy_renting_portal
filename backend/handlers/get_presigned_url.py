"""GetPresignedUrl Lambda handler for the Purdy Renting platform.

Generates a presigned S3 PUT URL that the frontend uses to upload a user file
(a Listado de Precios or a DAI file) directly to S3, bypassing Lambda for the
file bytes. The handler authenticates the caller via the Cognito authorizer
claims, validates the request body, and returns the upload URL together with
the unique S3 key where the object will be stored.

API route: POST /requests/presigned-url  (Cognito auth)

Requirements covered: 3.1, 3.2, 3.5, 10.4
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
import uuid
from typing import Any, Dict, Optional

import boto3

from utils.responses import ErrorCode, error_response, success_response
from utils.validators import validate_file_extension

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

#: Environment variable holding the target S3 bucket name.
FILES_BUCKET_ENV = "FILES_BUCKET"

#: Presigned PUT URL expiry, in seconds (5 minutes per design).
PRESIGNED_URL_EXPIRY_SECONDS = 300

#: Valid values for the ``fileType`` field.
VALID_FILE_TYPES = {"listado_precios", "dai"}

# Module-level S3 client so it can be reused across warm Lambda invocations.
_s3_client = None


def _get_s3_client():
    """Return a lazily-initialized, reusable boto3 S3 client."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _extract_user_email(event: Dict[str, Any]) -> Optional[str]:
    """Extract the authenticated user's email from Cognito authorizer claims.

    Returns the email string, or ``None`` when the claim is absent (which
    should only happen if the request bypassed the Cognito authorizer).
    """
    try:
        claims = event["requestContext"]["authorizer"]["claims"]
    except (KeyError, TypeError):
        return None

    if not isinstance(claims, dict):
        return None

    email = claims.get("email")
    if isinstance(email, str) and email.strip():
        return email.strip()
    return None


def _parse_body(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse the request body into a dict.

    Supports both a raw dict body (direct invocation / tests) and a
    JSON-encoded string body (API Gateway proxy integration). Returns ``None``
    when the body is missing or cannot be parsed into an object.
    """
    body = event.get("body")

    if body is None:
        return None

    if isinstance(body, dict):
        return body

    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8", errors="replace")

    if isinstance(body, str):
        try:
            parsed = json.loads(body)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    return None


def _sanitize_filename(filename: str) -> str:
    """Return a filesystem/S3-safe version of *filename*.

    Strips any directory components, normalizes unicode, and keeps only a
    conservative set of characters (letters, digits, dot, dash, underscore).
    All other characters are replaced with underscores. This protects against
    path traversal and control/script content in the S3 key (Requirement 10.4).
    """
    # Drop any path components a client may have included.
    base = filename.replace("\\", "/").split("/")[-1]

    # Normalize accented characters to their ASCII form where possible.
    normalized = unicodedata.normalize("NFKD", base)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")

    # Replace any character outside the safe allow-list with an underscore.
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", ascii_only)

    # Collapse repeated underscores and trim leading/trailing separators.
    sanitized = re.sub(r"_+", "_", sanitized).strip("._-")

    return sanitized or "archivo"


# --------------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------------- #


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Generate a presigned S3 PUT URL for a user file upload.

    Input (body):
        fileName: str - Original filename (must end in .xls/.xlsx/.csv)
        contentType: str - MIME type used to sign the upload
        fileType: str - "listado_precios" or "dai"

    Output (200):
        uploadUrl: str - Presigned PUT URL (expires in 300 seconds)
        s3Key: str - The S3 key where the file will be stored

    Errors:
        400 INVALID_FILE_FORMAT   - filename has a disallowed extension
        400 MISSING_REQUIRED_FIELD - missing fileName/contentType/fileType or
                                     an invalid fileType value
        401 UNAUTHORIZED          - no authenticated user email in claims
        500 INTERNAL_ERROR        - misconfiguration or presign failure
    """
    # --- Authentication ---------------------------------------------------- #
    user_email = _extract_user_email(event)
    if user_email is None:
        return error_response(ErrorCode.UNAUTHORIZED)

    # --- Body validation --------------------------------------------------- #
    body = _parse_body(event)
    if body is None:
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)

    file_name = body.get("fileName")
    content_type = body.get("contentType")
    file_type = body.get("fileType")

    # All three fields are required and must be non-empty strings.
    if not isinstance(file_name, str) or not file_name.strip():
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)
    if not isinstance(content_type, str) or not content_type.strip():
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)
    if not isinstance(file_type, str) or file_type not in VALID_FILE_TYPES:
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)

    file_name = file_name.strip()
    content_type = content_type.strip()

    # --- File extension validation ---------------------------------------- #
    if not validate_file_extension(file_name):
        return error_response(ErrorCode.INVALID_FILE_FORMAT)

    # --- Bucket configuration --------------------------------------------- #
    bucket = os.environ.get(FILES_BUCKET_ENV)
    if not bucket:
        # Misconfiguration: the deployment did not provide the bucket name.
        return error_response(ErrorCode.INTERNAL_ERROR)

    # --- Build the unique S3 key ------------------------------------------ #
    request_id = str(uuid.uuid4())
    safe_filename = _sanitize_filename(file_name)
    s3_key = f"uploads/{request_id}/{file_type}_{safe_filename}"

    # --- Generate the presigned PUT URL ----------------------------------- #
    try:
        upload_url = _get_s3_client().generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": bucket,
                "Key": s3_key,
                "ContentType": content_type,
            },
            ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
        )
    except Exception:  # noqa: BLE001 - surface a generic 500 to the caller
        return error_response(ErrorCode.STORAGE_ERROR)

    return success_response({"uploadUrl": upload_url, "s3Key": s3_key})
