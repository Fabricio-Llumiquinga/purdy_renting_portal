"""UpdateStatus Lambda handler for the Purdy Renting platform.

Robot-only endpoint that updates the processing status of a request. The Robot
authenticates with an API key that API Gateway validates at the gateway level
via a usage plan; this handler additionally performs a defensive presence check
of the API key identity on the incoming event.

API route: PUT /requests/{id}/status  (API Key auth)

Process:
    1. Defensively confirm an API key identity is present -> 401 otherwise.
    2. Read the request identifier from the path parameter ``id`` and the body
       fields ``status`` and optional ``observation``.
    3. Validate the ``status`` value against ``VALID_STATUSES`` -> 400 otherwise.
    4. Validate the ``observation`` length (<= 500 chars) when provided -> 400.
    5. Load the request record from DynamoDB (PK=REQUEST#{id}, SK=METADATA);
       404 when it does not exist.
    6. Reject updates when the current status is terminal
       (Procesado/Failed) -> 409.
    7. Validate the status transition with ``validate_status_transition`` and
       reject invalid transitions -> 409/400 as appropriate.
    8. Persist the new status, optional observation, and ``updatedAt`` timestamp.
    9. Return ``{message, updatedAt}`` via ``success_response``.

Environment variables:
    REQUESTS_TABLE: Name of the DynamoDB table holding request records.

Requirements covered: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3

from utils.responses import ErrorCode, error_response, success_response
from utils.validators import (
    MAX_OBSERVATION_LENGTH,
    TERMINAL_STATUSES,
    VALID_STATUSES,
    validate_status_transition,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

#: Environment variable holding the DynamoDB requests table name.
REQUESTS_TABLE_ENV = "REQUESTS_TABLE"

# Lazily-initialised DynamoDB resource so it can be reused across warm Lambda
# invocations and patched in tests.
_dynamodb_resource = None


def _get_table():
    """Return the DynamoDB table resource for the requests table.

    Raises:
        RuntimeError: If the ``REQUESTS_TABLE`` environment variable is unset.
    """
    global _dynamodb_resource

    table_name = os.environ.get(REQUESTS_TABLE_ENV)
    if not table_name:
        raise RuntimeError("REQUESTS_TABLE environment variable is not set")

    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb")

    return _dynamodb_resource.Table(table_name)


def _has_api_key_identity(event: Dict[str, Any]) -> bool:
    """Return True if the event carries an API key identity.

    API Gateway validates the API key against a usage plan before invoking the
    Lambda, so a request that reaches this handler has already been
    authenticated. This is a defensive, in-handler check that the identity
    context is present (Requirement 7.7, 7.8).
    """
    request_context = event.get("requestContext")
    if not isinstance(request_context, dict):
        return False

    identity = request_context.get("identity")
    if not isinstance(identity, dict):
        return False

    api_key = identity.get("apiKey")
    return bool(api_key and str(api_key).strip())


def _extract_request_id(event: Dict[str, Any]) -> Optional[str]:
    """Extract the request identifier from the ``id`` path parameter.

    Route: ``PUT /requests/{id}/status``. Returns ``None`` when the path
    parameter is missing or empty.
    """
    path_parameters = event.get("pathParameters")
    if not isinstance(path_parameters, dict):
        return None

    request_id = path_parameters.get("id")
    if not request_id or not str(request_id).strip():
        return None

    return str(request_id).strip()


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
        if isinstance(parsed, dict):
            return parsed

    return None


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Update the status of a request (Robot-only endpoint).

    Args:
        event: API Gateway proxy event. Expected to contain the ``id`` path
            parameter and a JSON body with ``status`` and optional
            ``observation``.
        context: Lambda context (unused).

    Returns:
        An API Gateway proxy response. On success the body is
        ``{"message": ..., "updatedAt": ...}``; on failure a standard error
        response.
    """
    # --- Auth (defensive API key presence check) --------------------------- #
    if not _has_api_key_identity(event):
        logger.warning("UpdateStatus invoked without an API key identity")
        return error_response(ErrorCode.UNAUTHORIZED)

    # --- Path parameter ---------------------------------------------------- #
    request_id = _extract_request_id(event)
    if not request_id:
        logger.warning("UpdateStatus invoked without a request id path parameter")
        return error_response(ErrorCode.REQUEST_NOT_FOUND)

    # --- Body validation --------------------------------------------------- #
    body = _parse_body(event)
    if body is None:
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)

    new_status = body.get("status")
    observation = body.get("observation")

    # Status is required and must be one of the allowed values (Requirement 7.5).
    if not isinstance(new_status, str) or new_status not in VALID_STATUSES:
        return error_response(ErrorCode.INVALID_STATUS)

    # Observation, when provided, must be a string within the length limit
    # (Requirement 7.3).
    if observation is not None:
        if not isinstance(observation, str):
            return error_response(ErrorCode.INVALID_STATUS)
        if len(observation) > MAX_OBSERVATION_LENGTH:
            return error_response(ErrorCode.OBSERVATION_TOO_LONG)

    # --- Load the request record ------------------------------------------- #
    try:
        table = _get_table()
    except RuntimeError:
        logger.exception("Requests table is not configured")
        return error_response(ErrorCode.INTERNAL_ERROR)

    try:
        result = table.get_item(
            Key={"PK": f"REQUEST#{request_id}", "SK": "METADATA"}
        )
    except Exception:  # noqa: BLE001 - surface a controlled 500 to the client
        logger.exception("Failed to load request from DynamoDB")
        return error_response(ErrorCode.DATABASE_ERROR)

    item = result.get("Item")
    if not item:
        logger.info("UpdateStatus: request %s not found", request_id)
        return error_response(ErrorCode.REQUEST_NOT_FOUND)

    current_status = item.get("status")

    # --- Terminal state guard (Requirement 7.6) ---------------------------- #
    if current_status in TERMINAL_STATUSES:
        logger.info(
            "UpdateStatus: request %s is in terminal state %s",
            request_id,
            current_status,
        )
        return error_response(ErrorCode.REQUEST_TERMINAL_STATE)

    # --- Transition validation (Requirement 7.5) --------------------------- #
    if not validate_status_transition(current_status, new_status):
        logger.info(
            "UpdateStatus: invalid transition %s -> %s for request %s",
            current_status,
            new_status,
            request_id,
        )
        return error_response(ErrorCode.INVALID_STATUS)

    # --- Persist the update ------------------------------------------------ #
    updated_at = datetime.now(timezone.utc).isoformat()

    update_expression_parts = ["#status = :status", "updatedAt = :updatedAt"]
    expression_attribute_names = {"#status": "status"}
    expression_attribute_values: Dict[str, Any] = {
        ":status": new_status,
        ":updatedAt": updated_at,
    }

    if observation is not None:
        update_expression_parts.append("observation = :observation")
        expression_attribute_values[":observation"] = observation

    update_expression = "SET " + ", ".join(update_expression_parts)

    try:
        table.update_item(
            Key={"PK": f"REQUEST#{request_id}", "SK": "METADATA"},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
        )
    except Exception:  # noqa: BLE001 - surface a controlled 500 to the client
        logger.exception("Failed to update request status in DynamoDB")
        return error_response(ErrorCode.DATABASE_ERROR)

    return success_response(
        {
            "message": "Estado actualizado correctamente.",
            "updatedAt": updated_at,
        }
    )
