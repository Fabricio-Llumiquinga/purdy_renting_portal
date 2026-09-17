"""CreateRequest Lambda handler for the Purdy Renting platform.

Creates a new request record after the user has uploaded both files to S3 via
presigned URLs. The handler authenticates the caller through the Cognito
authorizer claims, validates the request body and the referenced S3 objects,
persists a request record to DynamoDB, triggers a (non-blocking) email
confirmation, and dispara el job de UiPath que procesa los archivos.

API route: POST /requests  (Cognito auth)

Requirements covered: 2.7, 3.1, 4.1, 4.2, 4.3, 5.1, 10.4
"""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from utils.responses import ErrorCode, error_response, success_response
from utils.validators import (
    INITIAL_STATUS,
    MAX_USER_FILE_SIZE,
    format_date_cr,
    validate_company,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

REQUESTS_TABLE_ENV = "REQUESTS_TABLE"
FILES_BUCKET_ENV = "FILES_BUCKET"
METADATA_SK = "METADATA"
UPLOAD_KEY_PREFIX = "uploads/"

_dynamodb_resource = None
_s3_client = None


def _get_table():
    global _dynamodb_resource
    table_name = os.environ.get(REQUESTS_TABLE_ENV)
    if not table_name:
        raise RuntimeError("REQUESTS_TABLE environment variable is not set")
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb")
    return _dynamodb_resource.Table(table_name)


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def _extract_user_claims(
    event: Dict[str, Any]
) -> Tuple[Optional[str], Optional[str]]:
    try:
        claims = event["requestContext"]["authorizer"]["claims"]
    except (KeyError, TypeError):
        return (None, None)
    if not isinstance(claims, dict):
        return (None, None)
    email = claims.get("email")
    email = email.strip() if isinstance(email, str) and email.strip() else None
    name = claims.get("name")
    name = name.strip() if isinstance(name, str) and name.strip() else None
    return (email, name)


def _parse_body(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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


def _filename_from_key(s3_key: str) -> str:
    last_segment = s3_key.rstrip("/").split("/")[-1]
    for prefix in ("listado_precios_", "dai_"):
        if last_segment.startswith(prefix):
            return last_segment[len(prefix):] or last_segment
    return last_segment


def _verify_s3_object(
    bucket: str, s3_key: str
) -> Tuple[bool, Optional[ErrorCode]]:
    try:
        response = _get_s3_client().head_object(Bucket=bucket, Key=s3_key)
    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        logger.warning("HeadObject failed for key %s (status %s)", s3_key, status)
        return (False, ErrorCode.MISSING_REQUIRED_FIELD)
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error verifying S3 object %s", s3_key)
        return (False, ErrorCode.STORAGE_ERROR)
    content_length = response.get("ContentLength")
    if isinstance(content_length, int) and content_length > MAX_USER_FILE_SIZE:
        return (False, ErrorCode.FILE_TOO_LARGE)
    return (True, None)


def _read_s3_as_base64(bucket: str, s3_key: str) -> Optional[str]:
    """Descarga un objeto de S3 y lo devuelve codificado en base64 (str)."""
    try:
        obj = _get_s3_client().get_object(Bucket=bucket, Key=s3_key)
        raw = obj["Body"].read()
        return base64.b64encode(raw).decode("ascii")
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo leer/base64 el objeto S3 %s", s3_key)
        return None


def _send_confirmation_email(
    *,
    recipient_email: str,
    user_name: str,
    company_name: str,
    company_code: str,
    created_at: datetime,
) -> None:
    try:
        from services.notification_service import send_submission_confirmation

        submission_date = format_date_cr(created_at)
        send_submission_confirmation(
            recipient_email=recipient_email,
            user_name=user_name,
            company_name=company_name,
            company_code=company_code,
            submission_date=submission_date,
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "Confirmation email could not be sent for %s; continuing.",
            recipient_email,
            exc_info=True,
        )


def _trigger_uipath_job(
    *, bucket: str, listado_precios_key: str, dai_key: str, request_id: str
) -> None:
    """Dispara el job de UiPath con los dos archivos en base64 (best-effort).

    Descarga ambos objetos de S3, los codifica en base64 y llama al servicio de
    UiPath. Cualquier fallo se registra pero NO bloquea la creacion de la
    solicitud (el usuario ya recibio confirmacion y el registro ya existe).

    - in_Archivo1Base64 = Listado de Precios
    - in_Archivo2Base64 = Catalogo DAI
    """
    try:
        archivo1_b64 = _read_s3_as_base64(bucket, listado_precios_key)
        archivo2_b64 = _read_s3_as_base64(bucket, dai_key)
        if not archivo1_b64 or not archivo2_b64:
            logger.error(
                "No se pudo preparar base64 para UiPath (request %s).", request_id
            )
            return

        from services.uipath_service import trigger_job

        ok = trigger_job(archivo1_b64, archivo2_b64)
        if ok:
            logger.info("Job de UiPath disparado para request %s.", request_id)
        else:
            logger.error("Fallo al disparar el job de UiPath para request %s.", request_id)
    except Exception:  # noqa: BLE001 - nunca bloquear la creacion de la solicitud
        logger.warning(
            "Excepcion al disparar UiPath para request %s; continuando.",
            request_id,
            exc_info=True,
        )


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    user_email, user_name = _extract_user_claims(event)
    if user_email is None:
        return error_response(ErrorCode.UNAUTHORIZED)

    body = _parse_body(event)
    if body is None:
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)

    listado_precios_key = body.get("listadoPreciosS3Key")
    dai_key = body.get("daiS3Key")
    company = body.get("company")

    if not isinstance(listado_precios_key, str) or not listado_precios_key.strip():
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)
    if not isinstance(dai_key, str) or not dai_key.strip():
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)
    if not isinstance(company, str) or not company.strip():
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)

    listado_precios_key = listado_precios_key.strip()
    dai_key = dai_key.strip()
    company = company.strip()

    is_valid_company, company_code = validate_company(company)
    if not is_valid_company or company_code is None:
        return error_response(ErrorCode.INVALID_COMPANY)

    if not listado_precios_key.startswith(UPLOAD_KEY_PREFIX):
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)
    if not dai_key.startswith(UPLOAD_KEY_PREFIX):
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)

    bucket = os.environ.get(FILES_BUCKET_ENV)
    if not bucket:
        logger.error("%s environment variable is not set", FILES_BUCKET_ENV)
        return error_response(ErrorCode.INTERNAL_ERROR)

    for s3_key in (listado_precios_key, dai_key):
        ok, err = _verify_s3_object(bucket, s3_key)
        if not ok and err is not None:
            return error_response(err)

    request_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    created_at_iso = created_at.isoformat()

    listado_precios_file_name = _filename_from_key(listado_precios_key)
    dai_file_name = _filename_from_key(dai_key)

    item: Dict[str, Any] = {
        "PK": f"REQUEST#{request_id}",
        "SK": METADATA_SK,
        "requestId": request_id,
        "userEmail": user_email,
        "company": company,
        "companyCode": company_code,
        "listadoPreciosS3Key": listado_precios_key,
        "listadoPreciosFileName": listado_precios_file_name,
        "daiS3Key": dai_key,
        "daiFileName": dai_file_name,
        "generatedFileName": None,
        "generatedFileS3Key": None,
        "status": INITIAL_STATUS,
        "observation": None,
        "createdAt": created_at_iso,
        "updatedAt": created_at_iso,
        "GSI1PK": f"USER#{user_email}",
        "GSI1SK": f"CREATED#{created_at_iso}",
    }

    try:
        table = _get_table()
    except RuntimeError:
        logger.exception("Requests table is not configured")
        return error_response(ErrorCode.INTERNAL_ERROR)

    try:
        table.put_item(Item=item)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to persist request record for %s", user_email)
        return error_response(ErrorCode.DATABASE_ERROR)

    # Confirmacion por correo (best-effort, no bloqueante).
    _send_confirmation_email(
        recipient_email=user_email,
        user_name=user_name or user_email,
        company_name=company,
        company_code=company_code,
        created_at=created_at,
    )

    # Disparo del job de UiPath con los archivos en base64 (best-effort).
    _trigger_uipath_job(
        bucket=bucket,
        listado_precios_key=listado_precios_key,
        dai_key=dai_key,
        request_id=request_id,
    )

    message = (
        f"Su solicitud ha sido creada exitosamente. "
        f"Número de solicitud: {request_id}. "
        f"Estado: {INITIAL_STATUS}."
    )
    return success_response(
        {"requestId": request_id, "message": message}, status_code=201
    )