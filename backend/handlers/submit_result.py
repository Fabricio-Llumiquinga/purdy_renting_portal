"""SubmitResult Lambda handler for the Purdy Renting platform.

Endpoint Robot-only que CIERRA una solicitud en una sola llamada, alimentando
el modulo de seguimiento. Recibe el resultado de la ejecucion del proceso RPA:

    - status:           "Success" | "Failed"   (obligatorio)
    - detail:           texto descriptivo del resultado (opcional)
    - type_failed:      "Business Exception" | "IT Exception" | ""  (opcional)
    - archivo_generado: contenido del archivo en base64 (opcional; tipico en
                        exito)
    - file_name:        nombre del archivo generado (requerido si viene
                        archivo_generado)

Comportamiento:
    1. Verifica presencia de API key (auth Robot, validada en API Gateway).
    2. Lee el id de la ruta y valida el body.
    3. Mapea status -> estado interno (Success->Procesado, Failed->Failed).
    4. Si viene archivo_generado (y status es exito), lo decodifica, valida
       tamano, y lo sube a S3 con SSE.
    5. Persiste en DynamoDB: status, detail, typeFailed, updatedAt y, si aplica,
       generatedFileName/generatedFileS3Key.
    6. No permite re-cerrar una solicitud ya terminal (Procesado/Failed) -> 409.

API route: POST /requests/{id}/result  (API Key auth - key propia del servicio)
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
from utils.validators import (
    MAX_DETAIL_LENGTH,
    MAX_GENERATED_FILE_SIZE,
    RESULT_STATUS_MAP,
    TERMINAL_STATUSES,
    VALID_FAILURE_TYPES,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

REQUESTS_TABLE_ENV = "REQUESTS_TABLE"
FILES_BUCKET_ENV = "FILES_BUCKET"
METADATA_SK = "METADATA"
GENERATED_KEY_PREFIX = "generated/"

_dynamodb = None
_s3_client = None


def _get_table():
    global _dynamodb
    table_name = os.environ.get(REQUESTS_TABLE_ENV)
    if not table_name:
        raise RuntimeError("REQUESTS_TABLE environment variable is not set")
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(table_name)


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def _has_api_key_identity(event: Dict[str, Any]) -> bool:
    """True si el evento trae identidad de API key (defensivo)."""
    rc = event.get("requestContext")
    if not isinstance(rc, dict):
        return False
    identity = rc.get("identity")
    if not isinstance(identity, dict):
        return False
    api_key = identity.get("apiKey")
    return bool(api_key and str(api_key).strip())


def _extract_request_id(event: Dict[str, Any]) -> Optional[str]:
    path_params = event.get("pathParameters")
    if not isinstance(path_params, dict):
        return None
    request_id = path_params.get("id")
    if not request_id or not str(request_id).strip():
        return None
    return str(request_id).strip()


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


def _sanitize_filename(filename: str) -> str:
    """Deja solo el nombre base y quita caracteres peligrosos para la S3 key."""
    base = filename.replace("\\", "/").split("/")[-1].strip()
    # Conservador: quita cualquier caracter de control.
    cleaned = "".join(c for c in base if c.isprintable()).strip()
    return cleaned or "archivo_generado.xlsx"


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    # --- Auth (presencia de API key) --------------------------------------- #
    if not _has_api_key_identity(event):
        logger.warning("SubmitResult invocado sin identidad de API key")
        return error_response(ErrorCode.UNAUTHORIZED)

    # --- Path param -------------------------------------------------------- #
    request_id = _extract_request_id(event)
    if not request_id:
        return error_response(ErrorCode.REQUEST_NOT_FOUND)

    # --- Body -------------------------------------------------------------- #
    body = _parse_body(event)
    if body is None:
        return error_response(ErrorCode.MISSING_REQUIRED_FIELD)

    raw_status = body.get("status")
    detail = body.get("detail")
    type_failed = body.get("type_failed")
    archivo_generado = body.get("archivo_generado")
    file_name = body.get("file_name")

    # status obligatorio y en el mapa (Success/Failed).
    if not isinstance(raw_status, str) or raw_status not in RESULT_STATUS_MAP:
        return error_response(ErrorCode.INVALID_STATUS)
    internal_status = RESULT_STATUS_MAP[raw_status]

    # detail opcional (string acotado).
    if detail is not None:
        if not isinstance(detail, str):
            return error_response(ErrorCode.INVALID_INPUT)
        if len(detail) > MAX_DETAIL_LENGTH:
            return error_response(ErrorCode.OBSERVATION_TOO_LONG)

    # type_failed opcional; si viene debe ser uno de los permitidos.
    if type_failed is not None:
        if not isinstance(type_failed, str) or type_failed not in VALID_FAILURE_TYPES:
            return error_response(ErrorCode.INVALID_INPUT)

    # archivo_generado opcional; si viene, file_name es obligatorio.
    has_file = isinstance(archivo_generado, str) and bool(archivo_generado)
    if has_file:
        if not isinstance(file_name, str) or not file_name.strip():
            return error_response(ErrorCode.MISSING_REQUIRED_FIELD)
        file_name = _sanitize_filename(file_name)

    # --- Cargar el registro ------------------------------------------------ #
    try:
        table = _get_table()
    except RuntimeError:
        logger.exception("Requests table no configurada")
        return error_response(ErrorCode.INTERNAL_ERROR)

    try:
        result = table.get_item(
            Key={"PK": f"REQUEST#{request_id}", "SK": METADATA_SK}
        )
    except (ClientError, BotoCoreError):
        logger.exception("Fallo get_item para request %s", request_id)
        return error_response(ErrorCode.DATABASE_ERROR)

    item = result.get("Item")
    if not item:
        return error_response(ErrorCode.REQUEST_NOT_FOUND)

    # No re-cerrar una solicitud ya terminal.
    if item.get("status") in TERMINAL_STATUSES:
        logger.info(
            "SubmitResult: request %s ya esta en estado terminal %s",
            request_id,
            item.get("status"),
        )
        return error_response(ErrorCode.REQUEST_TERMINAL_STATE)

    # --- Subir archivo generado (si viene) --------------------------------- #
    generated_s3_key = None
    if has_file:
        try:
            decoded = base64.b64decode(archivo_generado, validate=True)
        except (binascii.Error, ValueError):
            return error_response(ErrorCode.INVALID_BASE64)
        if len(decoded) > MAX_GENERATED_FILE_SIZE:
            return error_response(ErrorCode.FILE_TOO_LARGE)

        bucket = os.environ.get(FILES_BUCKET_ENV)
        if not bucket:
            logger.error("%s no configurado", FILES_BUCKET_ENV)
            return error_response(ErrorCode.INTERNAL_ERROR)

        generated_s3_key = f"{GENERATED_KEY_PREFIX}{request_id}/{file_name}"
        try:
            _get_s3_client().put_object(
                Bucket=bucket,
                Key=generated_s3_key,
                Body=decoded,
                ServerSideEncryption="AES256",
            )
        except (ClientError, BotoCoreError):
            logger.exception("Fallo put_object para %s", generated_s3_key)
            # No actualizar DynamoDB si falla el almacenamiento.
            return error_response(ErrorCode.STORAGE_ERROR)

    # --- Persistir el resultado -------------------------------------------- #
    updated_at = datetime.now(timezone.utc).isoformat()

    set_parts = [
        "#status = :status",
        "detail = :detail",
        "typeFailed = :typeFailed",
        "updatedAt = :updatedAt",
    ]
    names = {"#status": "status"}
    values: Dict[str, Any] = {
        ":status": internal_status,
        ":detail": detail if detail is not None else None,
        ":typeFailed": type_failed if type_failed is not None else None,
        ":updatedAt": updated_at,
    }

    if generated_s3_key is not None:
        set_parts.append("generatedFileName = :genName")
        set_parts.append("generatedFileS3Key = :genKey")
        values[":genName"] = file_name
        values[":genKey"] = generated_s3_key

    try:
        table.update_item(
            Key={"PK": f"REQUEST#{request_id}", "SK": METADATA_SK},
            UpdateExpression="SET " + ", ".join(set_parts),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    except (ClientError, BotoCoreError):
        logger.exception("Fallo update_item para request %s", request_id)
        return error_response(ErrorCode.DATABASE_ERROR)

    logger.info(
        "SubmitResult: request %s cerrado como %s (archivo=%s)",
        request_id,
        internal_status,
        bool(generated_s3_key),
    )

    return success_response(
        {
            "message": "Resultado registrado correctamente.",
            "requestId": request_id,
            "status": internal_status,
            "generatedFileS3Key": generated_s3_key,
            "updatedAt": updated_at,
        }
    )
