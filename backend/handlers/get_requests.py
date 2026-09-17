"""GetRequests Lambda handler for the Purdy Renting platform.

Retrieves all requests belonging to the authenticated user. The user's email
is taken from the Cognito authorizer claims so that a user can only ever query
their own requests (Requirement 10.3 — user isolation).

Requests are fetched from DynamoDB via the ``GSI1`` global secondary index,
which is keyed on ``GSI1PK = USER#{userEmail}`` and sorted by
``GSI1SK = CREATED#{createdAt}``. Querying with ``ScanIndexForward=False``
returns items ordered by ``createdAt`` descending (Requirement 6.1, 6.2).

Environment variables:
    REQUESTS_TABLE: Name of the DynamoDB table holding request records.

Auth: Cognito Authorizer.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

from utils.responses import ErrorCode, error_response, success_response

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Name of the GSI used to query requests by user, ordered by creation date.
GSI1_INDEX_NAME = "GSI1"

# Response fields mapped from each DynamoDB item (Requirement 6.1).
_RESPONSE_FIELDS = (
    "requestId",
    "userEmail",
    "company",
    "companyCode",
    "listadoPreciosS3Key",
    "daiS3Key",
    "generatedFileName",
    "generatedFileS3Key",
    "status",
    "observation",
    "createdAt",
    "updatedAt",
)

# Lazily-initialised DynamoDB resource so tests can patch/mocking works and the
# resource is reused across warm Lambda invocations.
_dynamodb_resource = None


def _get_table():
    """Return the DynamoDB table resource for the requests table.

    Raises:
        RuntimeError: If the ``REQUESTS_TABLE`` environment variable is unset.
    """
    global _dynamodb_resource

    table_name = os.environ.get("REQUESTS_TABLE")
    if not table_name:
        raise RuntimeError("REQUESTS_TABLE environment variable is not set")

    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb")

    return _dynamodb_resource.Table(table_name)


def _extract_user_email(event: Dict[str, Any]) -> Optional[str]:
    """Extract the authenticated user's email from Cognito authorizer claims.

    Args:
        event: The API Gateway (Lambda proxy) event.

    Returns:
        The user's email if present in the claims, otherwise ``None``.
    """
    try:
        claims = event["requestContext"]["authorizer"]["claims"]
    except (KeyError, TypeError):
        return None

    email = claims.get("email") if isinstance(claims, dict) else None
    if not email or not str(email).strip():
        return None

    return str(email).strip()


def _map_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Map a raw DynamoDB item to the API response shape.

    Only the fields relevant to the client are projected. Nullable fields
    (``generatedFileName``, ``generatedFileS3Key``, ``observation``) default to
    ``None`` when absent so the response shape is consistent across items.

    Args:
        item: A DynamoDB item as returned by the SDK.

    Returns:
        A dict containing the response fields for a single request.
    """
    return {field: item.get(field) for field in _RESPONSE_FIELDS}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Return all requests for the authenticated user ordered by createdAt DESC.

    Args:
        event: API Gateway proxy event containing Cognito claims.
        context: Lambda context (unused).

    Returns:
        An API Gateway proxy response. On success the body is
        ``{"requests": [...]}``; on failure a standard error response.
    """
    user_email = _extract_user_email(event)
    if not user_email:
        logger.warning("GetRequests invoked without a valid user email in claims")
        return error_response(ErrorCode.UNAUTHORIZED)

    try:
        table = _get_table()
    except RuntimeError:
        logger.exception("Requests table is not configured")
        return error_response(ErrorCode.INTERNAL_ERROR)

    items: List[Dict[str, Any]] = []
    try:
        query_kwargs: Dict[str, Any] = {
            "IndexName": GSI1_INDEX_NAME,
            "KeyConditionExpression": Key("GSI1PK").eq(f"USER#{user_email}"),
            # Sort by GSI1SK (CREATED#{createdAt}) descending -> newest first.
            "ScanIndexForward": False,
        }

        response = table.query(**query_kwargs)
        items.extend(response.get("Items", []))

        # Follow pagination so all of the user's requests are returned.
        while "LastEvaluatedKey" in response:
            response = table.query(
                ExclusiveStartKey=response["LastEvaluatedKey"], **query_kwargs
            )
            items.extend(response.get("Items", []))
    except Exception:  # noqa: BLE001 - surface a controlled 500 to the client
        logger.exception("Failed to query requests for user")
        return error_response(ErrorCode.DATABASE_ERROR)

    requests = [_map_item(item) for item in items]
    return success_response({"requests": requests})
