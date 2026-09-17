"""Lambda handler: UploadGeneratedFile (Robot API).

Allows the Robot to upload the generated Excel file for a processed request.
The file is delivered as base64-encoded content, decoded, size-validated, and
stored in S3 with server-side encryption. On a successful upload the request's
DynamoDB record is updated with the generated file name and S3 key.

Authentication is enforced at the API Gateway layer via an API key / usage
plan. This handler additionally performs a defensive check on the request
context so that an invocation lacking the expected authorization context is
rejected with a 401 rather than proceeding unauthenticated (Requirement 8,
design "Auth: API Key").

API route: POST /requests/{id}/file  (API Key auth)

Requirements covered:
    8.1 - Decode the base64 file and store it in S3.
    8.2 - Update the DynamoDB record with the generated file name.
    8.3 - Reject malformed base64 with a 400 response.
    8.4 - Return 404 when the request identifier does not exist.
    8.5 - Reject files whose decoded size exceeds 50 MB with a 400 response.
    8.6 - On S3 failure, return 500 and do NOT update DynamoDB.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from utils.responses import ErrorCode, error_response, success_response
from utils.validators import MAX_GENERATED_FILE_SIZE

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

#: DynamoDB table holding request records (single-table design).
REQUESTS_TABLE = os.environ.get("REQUESTS_TABLE", "PurdyRentingRequests")

#: S3 bucket where generated files are stored.
FILES_BUCKET = os.environ.get("FILES_BUCKET", "purdy-renting-files")

#: Sort key value for request metadata items.
METADATA_SK = "METADATA"

_dynamodb = boto3.resource("dynamodb")
_s3_client = boto3.client("s3")


def _request_pk(request_id: str) -> str:
    """Build the partition key for a request record."""
    return f"REQUEST#{request_id}"


def _is_authenticated(event: Dict[str, Any]) -> bool:
    """Return True when the invocation carries an API Gateway request context.

    API key authentication is enforced by API Gateway's usage plan before the
    Lambda is invoked, so a genuine request always carries a ``requestContext``.
    This defensive check rejects invocations that lack it (Requirement 8,
    401 on missing/invalid API key).
    """
    request_context = event.get("requestContext")
    return isinstance(request_context, dict) and bool(request_context)


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


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Store a Robot-generated file for a request and update its record.

    Input:
        pathParameters.id: str - UUID of the request (route /requests/{id}/file)
        body.fileContent: str  - Base64-encoded file content
        body.fileName: str      - Name for the generated file

    Output (200):
        message: str - Confirmation message
        s3Key: str   - S3 key of the stored file

    Errors:
        400 INVALID_BASE64      - fileContent is not valid base64
        400 FILE_TOO_LARGE      - decoded size exceeds 50 MB
        400 MISSING_REQUIRED_FIELD - missing fileContent/fileName or body
        401 UNAUTHORIZED        - missing API Gateway request context
        404 REQUEST_NOT_FOUND   - request id does not exist
        500 STORAGE_ERROR       - S3 upload failed (DynamoDB left unchanged)
        500 DATABASE_ERROR      - DynamoDB read/write failed
    """
    # ----- Authentication (defensive) ------------------------------------- #
    if not _is_authenticated(event):
        logger.warning("Missing request context; rejecting as unauthorized")
        return error_response(ErrorCode.UNAUTHORIZED)

    # ----- Extract request id from path parameter ------------------------- #
    path_params = event.get("pathParameters") or {}
    request_id = path_params.get("id")
    if not request_id:
        return error_response(ErrorCode.REQUEST_NOT_FOUND)

    # ----- Body validation ------------------------------------------------ #
    body = _parse_body(event)
    if body is None:
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)

    file_content = body.get("fileContent")
    file_name = body.get("fileName")

    if not isinstance(file_content, str) or not file_content:
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)
    if not isinstance(file_name, str) or not file_name.strip():
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)

    file_name = file_name.strip()

    # ----- Retrieve the request record from DynamoDB ---------------------- #
    table = _dynamodb.Table(REQUESTS_TABLE)
    try:
        result = table.get_item(
            Key={"PK": _request_pk(request_id), "SK": METADATA_SK}
        )
    except ClientError:
        logger.exception("DynamoDB get_item failed for request %s", request_id)
        return error_response(ErrorCode.DATABASE_ERROR)

    item = result.get("Item")
    if not item:
        return error_response(ErrorCode.REQUEST_NOT_FOUND)

    # ----- Decode base64 content ------------------------------------------ #
    try:
        decoded = base64.b64decode(file_content, validate=True)
    except (binascii.Error, ValueError):
        return error_response(ErrorCode.INVALID_BASE64)

    # ----- Validate decoded size ------------------------------------------ #
    if len(decoded) > MAX_GENERATED_FILE_SIZE:
        return error_response(ErrorCode.FILE_TOO_LARGE)

    # ----- Upload to S3 with server-side encryption ----------------------- #
    s3_key = f"generated/{request_id}/{file_name}"
    try:
        _s3_client.put_object(
            Bucket=FILES_BUCKET,
            Key=s3_key,
            Body=decoded,
            ServerSideEncryption="AES256",
        )
    except (ClientError, BotoCoreError):
        logger.exception("S3 put_object failed for key %s", s3_key)
        # Requirement 8.6: do NOT update DynamoDB when storage fails.
        return error_response(ErrorCode.STORAGE_ERROR)

    # ----- Update the DynamoDB record ------------------------------------- #
    updated_at = datetime.now(timezone.utc).isoformat()
    try:
        table.update_item(
            Key={"PK": _request_pk(request_id), "SK": METADATA_SK},
            UpdateExpression=(
                "SET generatedFileName = :name, "
                "generatedFileS3Key = :key, "
                "updatedAt = :updatedAt"
            ),
            ExpressionAttributeValues={
                ":name": file_name,
                ":key": s3_key,
                ":updatedAt": updated_at,
            },
        )
    except ClientError:
        logger.exception(
            "DynamoDB update_item failed for request %s after S3 upload",
            request_id,
        )
        return error_response(ErrorCode.DATABASE_ERROR)

    return success_response(
        {"message": "Archivo generado almacenado correctamente.", "s3Key": s3_key}
    )
