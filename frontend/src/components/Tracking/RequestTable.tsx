// components/Tracking/RequestTable.tsx
//
// Request Tracking View table (see design.md "Request Tracking View" and
// Requirement 6). It lists the authenticated user's requests, newest first,
// rendering one RequestRow per request.
//
// Columns (Requirement 6.1): Fecha, Tipo Solicitud, Empresa,
// Nombre Listado Generado, Estado.
//
// Data (Requirements 6.1, 6.2): sourced from the `useRequests` hook, which
// fetches on mount and returns requests ordered by submission date descending
// (order is preserved here).
//
// States:
//   - Loading: Spanish message while the initial fetch is in flight.
//   - Error: Spanish message when the fetch fails (Requirement 6.6).
//   - Empty: Spanish message when the user has no requests.
//
// All text is Spanish (Requirements 9.1, 9.3).

import { useRequests } from '../../hooks/useRequests';
import { RequestRow } from './RequestRow';

/** Spanish column headers for the tracking table (Requirement 6.1). */
const COLUMN_HEADERS = [
  'Fecha',
  'Tipo Solicitud',
  'Empresa',
  'Nombre Listado Generado',
  'Estado',
] as const;

/** Spanish message shown while requests are being loaded. */
const LOADING_MESSAGE = 'Cargando solicitudes…';

/** Spanish message shown when the user has no requests yet. */
const EMPTY_MESSAGE = 'No hay solicitudes para mostrar.';

/**
 * Table listing the authenticated user's submitted requests along with their
 * processing status and generated-file download link.
 */
export function RequestTable() {
  const { requests, loading, error } = useRequests();

  if (loading) {
    return (
      <p className="request-table__loading" role="status">
        {LOADING_MESSAGE}
      </p>
    );
  }

  if (error) {
    return (
      <p className="request-table__error" role="alert">
        {error}
      </p>
    );
  }

  if (requests.length === 0) {
    return <p className="request-table__empty">{EMPTY_MESSAGE}</p>;
  }

  return (
    <table className="request-table">
      <thead>
        <tr>
          {COLUMN_HEADERS.map((header) => (
            <th key={header} scope="col">
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {requests.map((request) => (
          <RequestRow key={request.requestId} request={request} />
        ))}
      </tbody>
    </table>
  );
}

export default RequestTable;
