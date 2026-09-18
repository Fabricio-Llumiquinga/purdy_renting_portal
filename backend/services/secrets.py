"""Lectura de secretos desde AWS Secrets Manager (con cache en memoria).

Centraliza el acceso a los secretos de integraciones (UiPath, webhook de
notificaciones) para no versionarlos en texto plano ni exponerlos como
variables de entorno en claro.

El secreto se espera como un JSON con las claves:
    {
        "uipath_client_secret":     "...",
        "notification_webhook_url": "..."
    }

La variable de entorno INTEGRATIONS_SECRET_ID debe contener el nombre o ARN
del secreto. Si no esta configurada o la lectura falla, las funciones devuelven
``None`` para la clave solicitada y el llamador puede recurrir a un fallback
(p.ej. una variable de entorno), lo que facilita pruebas locales.

El resultado se cachea a nivel de modulo para reutilizarse entre invocaciones
"calientes" de la misma Lambda.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

#: Variable de entorno con el nombre/ARN del secreto de integraciones.
INTEGRATIONS_SECRET_ID_ENV = "INTEGRATIONS_SECRET_ID"

_secrets_client = None
_cache: Optional[Dict[str, str]] = None
_cache_loaded = False


def _get_client():
    global _secrets_client
    if _secrets_client is None:
        _secrets_client = boto3.client("secretsmanager")
    return _secrets_client


def _load() -> Dict[str, str]:
    """Carga y cachea el secreto de integraciones. Nunca lanza excepcion."""
    global _cache, _cache_loaded
    if _cache_loaded:
        return _cache or {}

    _cache_loaded = True  # marcar como intentado aunque falle, para no reintentar en caliente
    secret_id = os.environ.get(INTEGRATIONS_SECRET_ID_ENV)
    if not secret_id or not secret_id.strip():
        logger.info(
            "%s no configurado; se usara el fallback por variables de entorno.",
            INTEGRATIONS_SECRET_ID_ENV,
        )
        _cache = {}
        return _cache

    try:
        resp = _get_client().get_secret_value(SecretId=secret_id.strip())
        raw = resp.get("SecretString")
        if not raw:
            logger.error("El secreto %s no contiene SecretString.", secret_id)
            _cache = {}
            return _cache
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            logger.error("El secreto %s no es un objeto JSON.", secret_id)
            _cache = {}
            return _cache
        _cache = {str(k): str(v) for k, v in parsed.items()}
        return _cache
    except (ClientError, BotoCoreError):
        logger.exception("No se pudo leer el secreto %s de Secrets Manager.", secret_id)
        _cache = {}
        return _cache
    except (ValueError, TypeError):
        logger.exception("El secreto %s no es JSON valido.", secret_id)
        _cache = {}
        return _cache


def get_secret_value(key: str, env_fallback: Optional[str] = None) -> Optional[str]:
    """Devuelve el valor de ``key`` del secreto, o el fallback por entorno.

    Args:
        key: Clave dentro del JSON del secreto.
        env_fallback: Nombre de una variable de entorno a usar si el secreto no
            trae la clave (util para desarrollo local).

    Returns:
        El valor (str) o ``None`` si no se encuentra ni en el secreto ni en el
        fallback.
    """
    value = _load().get(key)
    if value:
        return value
    if env_fallback:
        env_value = os.environ.get(env_fallback)
        if env_value:
            return env_value
    return None
