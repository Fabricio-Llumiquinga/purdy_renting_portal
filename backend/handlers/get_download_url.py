"""Lambda handler: GetDownloadUrl.

Generates a presigned S3 GET URL so an authenticated User can download the
Robot-generated file associated with one of their requests.

The handler enforces ownership: a User may only download files belonging to
requests they submitted. When a request belongs to another User the handler
returns a 403 FORBIDDEN response without revealing whether the resource exists
(Requirement 10.7). When the request exists but has no generated file yet, a
404 REQUEST_NOT_FOUND response is returned.

Requirements covered:
    6.3 - Generated file is exposed as a downloadable link (name + URL).
    6.5 - Clicking the generated file name initiates a download from S3.
    10.3 - A User can only download files from their own requests.
    10.7 - Accessing another User's request returns 403 without leaking details.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

from utils.responses import ErrorCode, error_response, success_response

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

#: DynamoDB table holding request records (single-table design).
REQUESTS_TABLE = os.environ.get("REQUESTS_TABLE", "PurdyRentingRequests")

#: S3 bucket where generated files are stored.
FILES_BUCKET = os.environ.get("FILES_BUCKET", "purdy-renting-files")

#: Presigned GET URL expiry in seconds (design: 600 seconds).
DOWNLOAD_URL_EXPIRY = 600

#: Sort key value for request metadata items.
METADATA_SK = "METADATA"

_dynamodb = boto3.resource("dynamodb")
_s3_client = boto3.client("s3")


def _request_pk(request_id: str) -> str:
    """Build the partition key for a request record."""
    return f"REQUEST#{request_id}"


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Generate a presigned S3 GET URL for a request's generated file.

    Args:
        event: API Gateway (Lambda proxy) event. Expects the authenticated
            user's email in ``requestContext.authorizer.claims.email`` and the
            request id in ``pathParameters.id``.
        context: Lambda context (unused).

    Returns:
        An API Gateway proxy response. On success the body contains
        ``downloadUrl`` and ``fileName``.
    """
    # ----- Extract authenticated user email ------------------------------- #
    try:
        user_email = event["requestContext"]["authorizer"]["claims"]["email"]
    except (KeyError, TypeError):
        logger.warning("Missing user email in Cognito claims")
        return error_response(ErrorCode.UNAUTHORIZED)

    if not user_email:
        return error_response(ErrorCode.UNAUTHORIZED)

    # ----- Extract request id from path parameter ------------------------- #
    path_params = event.get("pathParameters") or {}
    request_id = path_params.get("id")
    if not request_id:
        return error_response(ErrorCode.REQUEST_NOT_FOUND)

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

    # ----- Ownership check ------------------------------------------------ #
    # A mismatch returns 403 FORBIDDEN without revealing resource details
    # (Requirement 10.7).
    if item.get("userEmail") != user_email:
        logger.warning(
            "User %s attempted to access request %s owned by another user",
            user_email,
            request_id,
        )
        return error_response(ErrorCode.FORBIDDEN)

    # ----- Ensure a generated file exists --------------------------------- #
    generated_key = item.get("generatedFileS3Key")
    if not generated_key:
        return error_response(ErrorCode.REQUEST_NOT_FOUND)

    file_name = item.get("generatedFileName") or os.path.basename(generated_key)

    # ----- Generate presigned GET URL ------------------------------------- #
    try:
        download_url = _s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": FILES_BUCKET,
                "Key": generated_key,
                "ResponseContentDisposition": (
                    f'attachment; filename="{file_name}"'
                ),
            },
            ExpiresIn=DOWNLOAD_URL_EXPIRY,
        )
    except ClientError:
        logger.exception(
            "Failed to generate presigned URL for key %s", generated_key
        )
        return error_response(ErrorCode.STORAGE_ERROR)

    return success_response({"downloadUrl": download_url, "fileName": file_name})
