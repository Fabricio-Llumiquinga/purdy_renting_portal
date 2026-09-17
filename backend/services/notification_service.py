"""Email notification service for the Purdy Renting platform.

Sends a submission-confirmation email to the user who created a request,
delivered through AWS SES. Delivery is best-effort: it retries a small number
of times with exponential backoff and never raises, so that a failed
notification cannot block or roll back the underlying request submission
(Requirement 5.4).

Requirements covered: 5.1, 5.2, 5.3, 5.4, 5.5
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Optional, Union

import boto3

from utils.validators import format_date_cr

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

logger = logging.getLogger(__name__)

#: Environment variable holding the verified SES sender address.
SES_SENDER_EMAIL_ENV = "SES_SENDER_EMAIL"

#: Number of send attempts before giving up (Requirement 5.4).
MAX_ATTEMPTS = 3

#: Exponential backoff delays (in seconds) applied between attempts:
#: after attempt 1 wait 1s, after attempt 2 wait 2s, after attempt 3 wait 4s.
_BACKOFF_SECONDS = (1, 2, 4)

#: Charset used for the SES message subject and body.
_CHARSET = "UTF-8"

# Module-level SES client, reused across warm Lambda invocations.
_ses_client = None


def _get_ses_client():
    """Return a lazily-initialized, reusable boto3 SES client."""
    global _ses_client
    if _ses_client is None:
        _ses_client = boto3.client("ses")
    return _ses_client


# --------------------------------------------------------------------------- #
# Message formatting
# --------------------------------------------------------------------------- #


def _format_submission_date(submission_date: Union[str, datetime]) -> str:
    """Return the submission date as a ``dd/MM/yyyy HH:mm`` string.

    Accepts either an already-formatted string (returned unchanged) or a
    ``datetime`` instance, which is formatted via ``format_date_cr``
    (Requirement 5.3).
    """
    if isinstance(submission_date, datetime):
        return format_date_cr(submission_date)
    return str(submission_date)


def _build_subject(company_code: str) -> str:
    """Build the email subject (Requirement 5.2).

    Format: ``Listado Precios - {company_code}`` where the code is "PM" for
    Purdy Motor and "AUTO" for Automotriz.
    """
    return f"Listado Precios - {company_code}"


def _build_body(user_name: str, submission_date: str, company_name: str) -> str:
    """Build the Spanish email body (Requirement 5.3).

    Includes the submitting user's name, the submission date in
    ``dd/MM/yyyy HH:mm`` format, and the selected company's full name.
    """
    return (
        f"Estimado(a) {user_name},\n\n"
        "Su solicitud de listado de precios ha sido recibida exitosamente.\n\n"
        f"Empresa: {company_name}\n"
        f"Fecha de envío: {submission_date}\n\n"
        "Le notificaremos cuando el listado generado esté disponible.\n\n"
        "Este es un mensaje automático, por favor no responda a este correo.\n\n"
        "Saludos cordiales,\n"
        "Plataforma Purdy Renting"
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
) -> bool:
    """Send a request-submission confirmation email via AWS SES.

    Args:
        recipient_email: The submitting user's email address.
        user_name: Display name of the submitting user.
        company_name: Full company name (e.g. "Purdy Motor" or "Automotriz").
        company_code: Short company code ("PM" or "AUTO") used in the subject.
        submission_date: Submission timestamp, either as a preformatted
            ``dd/MM/yyyy HH:mm`` string or as a ``datetime`` (which will be
            formatted via ``format_date_cr``).

    Behavior:
        - Subject: ``Listado Precios - {company_code}`` (Requirement 5.2).
        - Body in Spanish including user name, submission date and company
          full name (Requirement 5.3).
        - Retries up to ``MAX_ATTEMPTS`` times with exponential backoff of
          1s, 2s, 4s between attempts (Requirement 5.4).
        - Never raises; failures are logged for observability.

    Returns:
        ``True`` if the email was accepted by SES, ``False`` if there is no
        recipient address (Requirement 5.5) or if all retries were exhausted
        (Requirement 5.4).
    """
    # --- No recipient on file: skip and warn (Requirement 5.5) ------------- #
    if not recipient_email or not str(recipient_email).strip():
        logger.warning(
            "Notificación omitida: no hay dirección de correo del destinatario "
            "disponible (empresa=%s).",
            company_name,
        )
        return False

    recipient_email = str(recipient_email).strip()

    # --- Sender configuration --------------------------------------------- #
    sender_email = os.environ.get(SES_SENDER_EMAIL_ENV)
    if not sender_email or not sender_email.strip():
        logger.error(
            "No se pudo enviar la notificación: la variable de entorno %s no "
            "está configurada.",
            SES_SENDER_EMAIL_ENV,
        )
        return False
    sender_email = sender_email.strip()

    # --- Build the message ------------------------------------------------- #
    formatted_date = _format_submission_date(submission_date)
    subject = _build_subject(company_code)
    body = _build_body(user_name, formatted_date, company_name)

    ses = _get_ses_client()

    # --- Send with retry + exponential backoff ----------------------------- #
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            ses.send_email(
                Source=sender_email,
                Destination={"ToAddresses": [recipient_email]},
                Message={
                    "Subject": {"Data": subject, "Charset": _CHARSET},
                    "Body": {"Text": {"Data": body, "Charset": _CHARSET}},
                },
            )
            return True
        except Exception as exc:  # noqa: BLE001 - best-effort delivery
            logger.warning(
                "Fallo al enviar la notificación (intento %d de %d) a %s: %s",
                attempt,
                MAX_ATTEMPTS,
                recipient_email,
                exc,
            )
            # Wait before the next attempt, but not after the final one.
            if attempt < MAX_ATTEMPTS:
                time.sleep(_BACKOFF_SECONDS[attempt - 1])

    # --- All attempts exhausted (Requirement 5.4) -------------------------- #
    logger.error(
        "No se pudo enviar la notificación de confirmación a %s tras %d "
        "intentos.",
        recipient_email,
        MAX_ATTEMPTS,
    )
    return False
