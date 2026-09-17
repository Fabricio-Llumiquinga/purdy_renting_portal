// components/Request/CompanySelector.tsx
//
// Dropdown (select) for choosing the company associated with a request.
//
// Behavior (see design.md "CompanySelector" and Requirements 2.3, 2.6, 9.1):
//  - Renders exactly two options: "Purdy Motor" and "Automotriz" (Requirement 2.3).
//  - All labels and placeholder text are in Spanish (Requirement 9.1).
//  - Exposes an optional inline error message (shown in Spanish) used by the
//    parent form when the User submits without selecting a company (Requirement 2.6).
//  - The selected value is typed to the Request["company"] union so callers cannot
//    pass unsupported company values.

import { useId } from 'react';
import type { Request } from '../../types';

/** The set of companies a User can select. Mirrors Request["company"]. */
export type Company = Request['company'];

/** The two allowed company options, in display order. */
const COMPANY_OPTIONS: readonly Company[] = ['Purdy Motor', 'Automotriz'];

export interface CompanySelectorProps {
  /** Currently selected company, or "" when nothing has been chosen yet. */
  value: Company | '';
  /** Callback invoked with the newly selected company value. */
  onChange: (company: Company) => void;
  /** Optional inline validation error message (already in Spanish). */
  error?: string;
}

/**
 * Company selection dropdown with Spanish labels and inline error support.
 */
export function CompanySelector({ value, onChange, error }: CompanySelectorProps) {
  const selectId = useId();
  const errorId = `${selectId}-error`;
  const hasError = Boolean(error);

  return (
    <div className="company-selector">
      <label htmlFor={selectId}>Empresa</label>
      <select
        id={selectId}
        value={value}
        onChange={(event) => onChange(event.target.value as Company)}
        aria-invalid={hasError || undefined}
        aria-describedby={hasError ? errorId : undefined}
      >
        <option value="" disabled>
          Seleccione una empresa
        </option>
        {COMPANY_OPTIONS.map((company) => (
          <option key={company} value={company}>
            {company}
          </option>
        ))}
      </select>
      {hasError && (
        <p id={errorId} role="alert" className="company-selector__error">
          {error}
        </p>
      )}
    </div>
  );
}

export default CompanySelector;
