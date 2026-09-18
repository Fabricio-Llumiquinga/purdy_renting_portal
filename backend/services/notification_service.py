"""Notification service for the Purdy Renting platform.

Envia la notificacion de confirmacion de solicitud a traves de un servicio
POST externo (Power Automate). La entrega es best-effort: reintenta un numero
pequeno de veces con backoff exponencial y NUNCA lanza excepcion, de modo que
una notificacion fallida no bloquee ni revierta la creacion de la solicitud
(Requirement 5.4).

Body enviado al servicio (schema acordado):
    {
        "destinatario":     str,   # correo del destinatario
        "asunto":           str,   # asunto del mensaje
        "enlaceUrl":        str,   # enlace opcional (p.ej. seguimiento)
        "ejecutivoNombre":  str,   # nombre del solicitante/ejecutivo
        "cuerpoHtml":       str    # cuerpo HTML del mensaje
    }

SEGURIDAD:
    - La URL del servicio contiene una firma (sig) y NO debe versionarse en
      texto plano. Se lee desde la variable de entorno NOTIFICATION_WEBHOOK_URL
      (provista en el deploy / Secrets Manager).

Requirements covered: 5.1, 5.2, 5.3, 5.4, 5.5
"""

from __future__ import annotations

import html
import json
import logging
import os
import time
from datetime import datetime
from typing import Optional, Union
from urllib import error as urllib_error
from urllib import request as urllib_request

from utils.validators import format_date_cr

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

logger = logging.getLogger(__name__)

#: Variable de entorno con la URL del servicio POST de notificaciones.
NOTIFICATION_WEBHOOK_URL_ENV = "NOTIFICATION_WEBHOOK_URL"

#: Numero de intentos de envio antes de rendirse (Requirement 5.4).
MAX_ATTEMPTS = 3

#: Backoff exponencial (segundos) entre intentos: 1s, 2s, 4s.
_BACKOFF_SECONDS = (1, 2, 4)

#: Timeout de red (segundos) para cada llamada HTTP.
_HTTP_TIMEOUT = int(os.environ.get("NOTIFICATION_HTTP_TIMEOUT", "15"))


# --------------------------------------------------------------------------- #
# Message formatting
# --------------------------------------------------------------------------- #


def _format_submission_date(submission_date: Union[str, datetime]) -> str:
    """Return the submission date as a ``dd/MM/yyyy HH:mm`` string."""
    if isinstance(submission_date, datetime):
        return format_date_cr(submission_date)
    return str(submission_date)


def _build_subject(company_code: str) -> str:
    """Build the email subject (Requirement 5.2).

    Format: ``Listado Precios - {company_code}``.
    """
    return f"Listado Precios - {company_code}"


def _esc(value: str) -> str:
    """Escapa texto para insertarlo de forma segura en el HTML del correo."""
    return html.escape(str(value or ""), quote=True)


def _build_html_body(
    user_name: str,
    submission_date: str,
    company_name: str,
    company_code: str = "",
    enlace_url: str = "",
) -> str:
    """Construye el cuerpo HTML ejecutivo del correo (Requirement 5.3).

    Diseño de correo (compatible con Outlook/Gmail): layout basado en tablas y
    estilos inline, con cabecera de marca, tarjeta de detalles y pie de pagina.
    Todos los valores dinamicos se escapan.
    """
    user = _esc(user_name)
    company = _esc(company_name)
    code = _esc(company_code)
    date = _esc(submission_date)
    link = _esc(enlace_url)

    # Boton opcional de seguimiento (solo si hay enlace).
    cta_block = ""
    if enlace_url:
        cta_block = (
            '<tr><td style="padding:8px 0 4px 0;">'
            f'<a href="{link}" target="_blank" '
            'style="display:inline-block;background-color:#AF2D76;color:#ffffff;'
            'text-decoration:none;font-weight:600;font-size:14px;'
            'padding:12px 22px;border-radius:8px;">Ver seguimiento de la solicitud</a>'
            "</td></tr>"
        )

    # Chip con el codigo de empresa (solo si viene).
    code_chip = ""
    if company_code:
        code_chip = (
            f'&nbsp;<span style="display:inline-block;background-color:#F6E4EE;'
            'color:#8E2360;font-size:12px;font-weight:600;padding:2px 8px;'
            f'border-radius:10px;">{code}</span>'
        )

    return (
        '<!DOCTYPE html>'
        '<html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        '<title>Confirmacion de solicitud</title></head>'
        '<body style="margin:0;padding:0;background-color:#FBF4F7;'
        'font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#2B2B2B;">'
        # Contenedor centrado
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background-color:#FBF4F7;padding:24px 12px;"><tr><td align="center">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;width:100%;background-color:#ffffff;'
        'border-radius:14px;overflow:hidden;'
        'box-shadow:0 2px 10px rgba(43,43,43,0.08);">'
        # Cabecera con degradado de marca
        '<tr><td style="background:linear-gradient(120deg,#AF2D76 0%,#C74C63 45%,'
        '#E39D3C 100%);padding:24px 32px;">'
        '<div style="color:#ffffff;font-size:22px;font-weight:700;'
        'letter-spacing:1px;">ANY<span style="color:#F6E4EE;">2</span>CLOUD</div>'
        '<div style="color:#F6E4EE;font-size:13px;margin-top:2px;">'
        'Plataforma Purdy Renting</div>'
        '</td></tr>'
        # Cuerpo
        '<tr><td style="padding:32px;">'
        '<h1 style="margin:0 0 4px 0;font-size:20px;color:#2B2B2B;">'
        'Solicitud recibida</h1>'
        '<p style="margin:0 0 20px 0;font-size:14px;color:#7A6B73;">'
        'Su solicitud de listado de precios se registro correctamente.</p>'
        f'<p style="margin:0 0 16px 0;font-size:15px;">Estimado(a) '
        f'<strong>{user}</strong>,</p>'
        '<p style="margin:0 0 20px 0;font-size:15px;line-height:1.5;">'
        'Hemos recibido su solicitud exitosamente. A continuacion el detalle:</p>'
        # Tarjeta de detalles
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background-color:#FBF4F7;border:1px solid #ECE1E8;'
        'border-radius:12px;padding:4px 0;margin-bottom:20px;">'
        '<tr><td style="padding:14px 18px;font-size:13px;color:#7A6B73;'
        'width:140px;">Empresa</td>'
        f'<td style="padding:14px 18px;font-size:14px;font-weight:600;'
        f'color:#2B2B2B;">{company}{code_chip}</td></tr>'
        '<tr><td style="padding:14px 18px;font-size:13px;color:#7A6B73;'
        'border-top:1px solid #ECE1E8;">Fecha de envio</td>'
        f'<td style="padding:14px 18px;font-size:14px;font-weight:600;'
        f'color:#2B2B2B;border-top:1px solid #ECE1E8;">{date}</td></tr>'
        '</table>'
        # CTA opcional
        '<table role="presentation" cellpadding="0" cellspacing="0">'
        f'{cta_block}</table>'
        '<p style="margin:20px 0 0 0;font-size:14px;line-height:1.5;color:#2B2B2B;">'
        'Le notificaremos cuando el listado generado este disponible.</p>'
        '</td></tr>'
        # Pie
        '<tr><td style="padding:20px 32px;background-color:#FBF4F7;'
        'border-top:1px solid #ECE1E8;">'
        '<p style="margin:0;font-size:12px;color:#7A6B73;line-height:1.5;">'
        'Este es un mensaje automatico, por favor no responda a este correo.<br>'
        'Saludos cordiales, Plataforma Purdy Renting.</p>'
        '</td></tr>'
        '</table>'
        '</td></tr></table>'
        '</body></html>'
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def send_submission_confirmation(
    recipient_email: str,
    user_name: str,
    company_name: str,
    company_code: str,
    submission_date: Union[str, datetime],
    enlace_url: Optional[str] = None,
) -> bool:
    """Envia la confirmacion de solicitud via el servicio POST externo.

    Args:
        recipient_email: Correo del destinatario.
        user_name: Nombre del usuario/ejecutivo solicitante.
        company_name: Nombre completo de la empresa (p.ej. "Purdy Motor").
        company_code: Codigo corto ("PM" o "AUTO") usado en el asunto.
        submission_date: Timestamp de envio (str preformateado o datetime).
        enlace_url: Enlace opcional (p.ej. de seguimiento) para el cuerpo.

    Behavior:
        - Asunto: ``Listado Precios - {company_code}`` (Requirement 5.2).
        - Cuerpo HTML en espanol con nombre, fecha y empresa (Requirement 5.3).
        - Reintenta hasta ``MAX_ATTEMPTS`` con backoff 1s/2s/4s (Req 5.4).
        - Nunca lanza; los fallos se registran.

    Returns:
        ``True`` si el servicio acepto la peticion (2xx), ``False`` si falta el
        destinatario (Requirement 5.5), la URL no esta configurada, o se
        agotaron los reintentos (Requirement 5.4).
    """
    # --- Sin destinatario: omitir y advertir (Requirement 5.5) ------------- #
    if not recipient_email or not str(recipient_email).strip():
        logger.warning(
            "Notificación omitida: no hay dirección de correo del destinatario "
            "disponible (empresa=%s).",
            company_name,
        )
        return False

    recipient_email = str(recipient_email).strip()

    # --- Configuracion de la URL del servicio ------------------------------ #
    # Prioridad: Secrets Manager (notification_webhook_url) -> env NOTIFICATION_WEBHOOK_URL.
    webhook_url = None
    try:
        from services.secrets import get_secret_value

        webhook_url = get_secret_value(
            "notification_webhook_url", env_fallback=NOTIFICATION_WEBHOOK_URL_ENV
        )
    except Exception:  # noqa: BLE001 - fallback a env
        webhook_url = os.environ.get(NOTIFICATION_WEBHOOK_URL_ENV)

    if not webhook_url or not webhook_url.strip():
        logger.error(
            "No se pudo enviar la notificación: no hay URL de webhook "
            "configurada (Secrets Manager ni %s).",
            NOTIFICATION_WEBHOOK_URL_ENV,
        )
        return False
    webhook_url = webhook_url.strip()

    # --- Construir el payload ---------------------------------------------- #
    formatted_date = _format_submission_date(submission_date)
    subject = _build_subject(company_code)
    html_body = _build_html_body(
        user_name,
        formatted_date,
        company_name,
        company_code=company_code,
        enlace_url=enlace_url or "",
    )

    payload = {
        "destinatario": recipient_email,
        "asunto": subject,
        "enlaceUrl": enlace_url or "",
        "ejecutivoNombre": user_name,
        "cuerpoHtml": html_body,
    }
    data = json.dumps(payload).encode("utf-8")

    # --- Enviar con reintentos + backoff exponencial ----------------------- #
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            req = urllib_request.Request(
                webhook_url,
                data=data,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            with urllib_request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                status = resp.getcode()
                if 200 <= status < 300:
                    return True
                logger.warning(
                    "El servicio de notificación respondió HTTP %s (intento %d de %d).",
                    status,
                    attempt,
                    MAX_ATTEMPTS,
                )
        except urllib_error.HTTPError as exc:
            logger.warning(
                "Fallo al enviar la notificación (intento %d de %d) a %s: HTTP %s %s",
                attempt,
                MAX_ATTEMPTS,
                recipient_email,
                exc.code,
                exc.reason,
            )
        except Exception as exc:  # noqa: BLE001 - best-effort delivery
            logger.warning(
                "Fallo al enviar la notificación (intento %d de %d) a %s: %s",
                attempt,
                MAX_ATTEMPTS,
                recipient_email,
                exc,
            )

        # Esperar antes del siguiente intento, pero no tras el ultimo.
        if attempt < MAX_ATTEMPTS:
            time.sleep(_BACKOFF_SECONDS[attempt - 1])

    # --- Reintentos agotados (Requirement 5.4) ----------------------------- #
    logger.error(
        "No se pudo enviar la notificación de confirmación a %s tras %d "
        "intentos.",
        recipient_email,
        MAX_ATTEMPTS,
    )
    return False
