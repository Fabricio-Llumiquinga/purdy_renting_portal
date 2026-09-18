"""UiPath Orchestrator integration service for the Purdy Renting platform.

Dispara un job de UiPath (Orchestrator) que procesa los dos archivos que el
usuario cargo (Listado de Precios y Catalogo DAI), enviados como cadenas
base64 en los argumentos in_Archivo1Base64 e in_Archivo2Base64.

Flujo (3 pasos, segun el contrato del servicio):
    1. Authenticate: POST al identity server -> access_token (Bearer).
    2. Start job:     POST a Orchestrator OData StartJobs con InputArguments.

SEGURIDAD:
    - El client_secret NUNCA debe vivir en el frontend. Se lee desde variables
      de entorno. Los valores por defecto aqui son solo para desarrollo/demo;
      en produccion usar AWS Secrets Manager y ROTAR el secreto (el secreto
      compartido en texto plano debe considerarse comprometido).

Requisitos: se invoca tras crear la solicitud (best-effort, no bloqueante).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Configuracion (por variables de entorno; defaults solo para desarrollo)
# --------------------------------------------------------------------------- #

# Paso 1 - Authenticate
UIPATH_TOKEN_URL = os.environ.get(
    "UIPATH_TOKEN_URL",
    "https://cloud.uipath.com/identity_/connect/token",
)
UIPATH_CLIENT_ID = os.environ.get(
    "UIPATH_CLIENT_ID", "8f64dac1-9ba3-4e42-a0f3-ca11aaff7dc2"
)
# NOTA: mover a Secrets Manager y rotar. Default solo para demo local.
UIPATH_CLIENT_SECRET = os.environ.get("UIPATH_CLIENT_SECRET", "")
UIPATH_SCOPE = os.environ.get(
    "UIPATH_SCOPE", "OR.Jobs OR.Execution OR.Folders"
)

# Paso 2 - Start job
UIPATH_JOBS_URL = os.environ.get(
    "UIPATH_JOBS_URL",
    "https://cloud.uipath.com/grupopurdyrentingcommunity/DefaultTenant/"
    "orchestrator_/odata/Jobs/UiPath.Server.Configuration.OData.StartJobs",
)
UIPATH_RELEASE_KEY = os.environ.get(
    "UIPATH_RELEASE_KEY", "94b379af-77fa-4320-b792-1682ef8171ac"
)
UIPATH_ORG_UNIT_ID = os.environ.get("UIPATH_ORG_UNIT_ID", "8073429")

# Timeout de red (segundos) para cada llamada HTTP.
_HTTP_TIMEOUT = int(os.environ.get("UIPATH_HTTP_TIMEOUT", "30"))

# User-Agent explicito: el identity server de UiPath (tras Cloudflare) responde
# 403 al User-Agent por defecto de urllib. Un UA de navegador/cliente comun pasa.
_USER_AGENT = os.environ.get(
    "UIPATH_USER_AGENT",
    "Mozilla/5.0 (compatible; PurdyRentingBackend/1.0)",
)


# --------------------------------------------------------------------------- #
# Paso 1: Authenticate
# --------------------------------------------------------------------------- #


def _resolve_client_secret() -> str:
    """Obtiene el client_secret desde Secrets Manager, con fallback a env.

    Prioridad: Secrets Manager (clave ``uipath_client_secret``) -> variable de
    entorno ``UIPATH_CLIENT_SECRET``. Nunca lanza excepcion.
    """
    try:
        from services.secrets import get_secret_value

        value = get_secret_value(
            "uipath_client_secret", env_fallback="UIPATH_CLIENT_SECRET"
        )
        if value:
            return value
    except Exception:  # noqa: BLE001 - fallback silencioso a env global
        logger.warning("No se pudo resolver el secreto de UiPath; se usa env.", exc_info=True)
    return UIPATH_CLIENT_SECRET


def _authenticate() -> Optional[str]:
    """Obtiene un access_token de UiPath via client_credentials.

    Returns:
        El access_token (str) o ``None`` si la autenticacion falla o falta el
        client_secret.
    """
    client_secret = _resolve_client_secret()
    if not client_secret:
        logger.error(
            "client_secret de UiPath no configurado; no se puede autenticar."
        )
        return None

    form = urllib_parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": UIPATH_CLIENT_ID,
            "client_secret": client_secret,
            "scope": UIPATH_SCOPE,
        }
    ).encode("utf-8")

    req = urllib_request.Request(
        UIPATH_TOKEN_URL,
        data=form,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            # UiPath (Cloudflare/WAF) rechaza (403) el User-Agent por defecto
            # de urllib. Enviar uno explicito evita el bloqueo.
            "User-Agent": _USER_AGENT,
        },
    )

    try:
        with urllib_request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        logger.error("UiPath auth HTTPError %s: %s", exc.code, exc.reason)
        return None
    except Exception:  # noqa: BLE001
        logger.exception("Fallo al autenticar con UiPath.")
        return None

    token = payload.get("access_token")
    if not token:
        logger.error("Respuesta de UiPath sin access_token.")
        return None
    return token


# --------------------------------------------------------------------------- #
# Paso 2: Start job
# --------------------------------------------------------------------------- #


def _start_job(
    token: str,
    archivo1_url: str,
    archivo2_url: str,
    nombre_empresa: str,
    id_solicitud: str,
) -> bool:
    """Dispara el job de UiPath con las URLs de descarga de los dos archivos.

    Se envian URLs presignadas de S3 (no el contenido base64), porque el campo
    InputArguments de UiPath esta limitado a 10.000 caracteres y el contenido
    en base64 lo excede. El robot descarga los archivos haciendo GET a las URLs.

    NOTA: se conservan los nombres de argumento del bot existente
    (in_Archivo1Base64 / in_Archivo2Base64); su CONTENIDO ahora es una URL de
    descarga, no base64. El workflow debe descargar desde esa URL.

    Args:
        token: access_token Bearer obtenido en _authenticate().
        archivo1_url: URL presignada del Listado de Precios (in_Archivo1Base64).
        archivo2_url: URL presignada del Listado DAI (in_Archivo2Base64).
        nombre_empresa: Nombre de la empresa del formulario (in_NombreEmpresa).
        id_solicitud: requestId de la solicitud (in_IdSolicitud); el robot lo usa
            para reportar el resultado via POST /requests/{id}/result.

    Returns:
        True si Orchestrator acepto la peticion (2xx), False en caso contrario.
    """
    # InputArguments debe ser un STRING JSON (JSON anidado), segun el contrato.
    input_arguments = json.dumps(
        {
            "in_Archivo1Base64": archivo1_url,
            "in_Archivo2Base64": archivo2_url,
            "in_NombreEmpresa": nombre_empresa,
            "in_IdSolicitud": id_solicitud,
        }
    )

    body = json.dumps(
        {
            "startInfo": {
                "ReleaseKey": UIPATH_RELEASE_KEY,
                "Strategy": "ModernJobsCount",
                "JobsCount": 1,
                "InputArguments": input_arguments,
            }
        }
    ).encode("utf-8")

    req = urllib_request.Request(
        UIPATH_JOBS_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UIPATH-OrganizationUnitId": UIPATH_ORG_UNIT_ID,
            "User-Agent": _USER_AGENT,
        },
    )

    try:
        with urllib_request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            status = resp.getcode()
            if 200 <= status < 300:
                logger.info("Job de UiPath disparado correctamente (HTTP %s).", status)
                return True
            logger.error("UiPath StartJobs respondio HTTP %s.", status)
            return False
    except urllib_error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:  # noqa: BLE001
            pass
        logger.error("UiPath StartJobs HTTPError %s: %s %s", exc.code, exc.reason, detail)
        return False
    except Exception:  # noqa: BLE001
        logger.exception("Fallo al disparar el job de UiPath.")
        return False


# --------------------------------------------------------------------------- #
# API publica
# --------------------------------------------------------------------------- #


def trigger_job(
    archivo1_url: str,
    archivo2_url: str,
    nombre_empresa: str = "",
    id_solicitud: str = "",
) -> bool:
    """Autentica y dispara el job de UiPath con las URLs de los dos archivos.

    Best-effort: nunca lanza excepcion. Devuelve True solo si ambos pasos
    (auth + start) fueron exitosos.

    Args:
        archivo1_url: URL presignada del Listado de Precios.
        archivo2_url: URL presignada del Listado DAI.
        nombre_empresa: Nombre de la empresa del formulario (in_NombreEmpresa).
        id_solicitud: requestId de la solicitud (in_IdSolicitud).
    """
    if not archivo1_url or not archivo2_url:
        logger.error("Faltan URLs de archivos para disparar el job de UiPath.")
        return False

    token = _authenticate()
    if not token:
        return False

    return _start_job(token, archivo1_url, archivo2_url, nombre_empresa, id_solicitud)