// components/Tracking/RequestRow.tsx
//
// Renders a single request as a table row (<tr>) inside the Request Tracking
// table. Estilo visual segun Manual de Identidad Any2cloud:
//   - Estado mostrado como badge con semantica de color (lima = exito).
//   - Nombre del listado generado como enlace de descarga en magenta.
//
// All text is Spanish (Requirement 9.1).

import { useState } from 'react';
import type { Request } from '../../types';
import { getDownloadUrl } from '../../services/requestService';
import { formatDateCR } from '../../utils/dateFormat';

const REQUEST_TYPE_LABEL = 'Listado de Precios';

const DOWNLOAD_ERROR_MESSAGE =
  'No se pudo descargar el archivo. Por favor, intentelo de nuevo.';

export interface RequestRowProps {
  request: Request;
}

// Mapa de estado -> clase modificadora para el badge.
// Semantica Any2cloud: verde lima solo para exito/confirmacion (Procesado).
const STATUS_CLASS: Record<Request['status'], string> = {
  'Procesado': 'status-badge--ok',
  'Procesando': 'status-badge--progress',
  'Pendiente de Procesar': 'status-badge--pending',
  'Failed': 'status-badge--failed',
};

function triggerBrowserDownload(url: string, fileName: string): void {
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
}

export function RequestRow({ request }: RequestRowProps) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasGeneratedFile = Boolean(
    request.generatedFileS3Key && request.generatedFileName,
  );

  async function handleDownload() {
    if (downloading) return;
    setError(null);
    setDownloading(true);
    try {
      const { downloadUrl, fileName } = await getDownloadUrl(request.requestId);
      triggerBrowserDownload(downloadUrl, fileName || request.generatedFileName || 'archivo');
    } catch {
      setError(DOWNLOAD_ERROR_MESSAGE);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <tr className="request-row">
      <td className="request-row__fecha">{formatDateCR(request.createdAt)}</td>
      <td className="request-row__tipo">{REQUEST_TYPE_LABEL}</td>
      <td className="request-row__empresa">{request.company}</td>
      <td className="request-row__generado">
        {hasGeneratedFile ? (
          <>
            <button
              type="button"
              className="request-row__download-link"
              onClick={handleDownload}
              disabled={downloading}
            >
              {downloading ? 'Descargando...' : request.generatedFileName}
            </button>
            {error && (
              <p role="alert" className="request-row__error">
                {error}
              </p>
            )}
          </>
        ) : (
          <span className="request-row__generado--empty">-</span>
        )}
      </td>
      <td className="request-row__estado">
        <span className={`status-badge ${STATUS_CLASS[request.status]}`}>
          {request.status}
        </span>
      </td>
    </tr>
  );
}

export default RequestRow;