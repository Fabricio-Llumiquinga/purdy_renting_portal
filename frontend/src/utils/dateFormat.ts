// utils/dateFormat.ts
//
// Shared date-formatting helpers for the Purdy Renting platform frontend.
//
// The platform displays dates in the Costa Rican convention "dd/MM/yyyy HH:mm"
// (see Requirement 9.3 and design.md "Request Tracking View"). Timestamps are
// stored and transported as ISO 8601 strings (Request.createdAt / updatedAt),
// so this helper converts an ISO 8601 string into that display format.

/** Pad a number to at least two digits (e.g. 5 -> "05"). */
function pad2(value: number): string {
  return value.toString().padStart(2, '0');
}

/**
 * Format an ISO 8601 date-time string as "dd/MM/yyyy HH:mm".
 *
 * The formatting uses the browser's local time zone, matching how a Costa Rican
 * user expects to see submission timestamps. Invalid or empty inputs return an
 * empty string so the UI can render a blank cell rather than "Invalid Date".
 *
 * @param isoString ISO 8601 timestamp (e.g. "2024-05-01T14:30:00Z").
 * @returns The formatted date string, or "" when the input cannot be parsed.
 */
export function formatDateCR(isoString: string | null | undefined): string {
  if (!isoString) {
    return '';
  }

  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return '';
  }

  const day = pad2(date.getDate());
  const month = pad2(date.getMonth() + 1);
  const year = date.getFullYear();
  const hours = pad2(date.getHours());
  const minutes = pad2(date.getMinutes());

  return `${day}/${month}/${year} ${hours}:${minutes}`;
}

export default formatDateCR;
