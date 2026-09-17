// components/Request/RequestForm.tsx
//
// Request submission form. This is the "Crear nueva solicitud" view: it
// composes two FileUpload slots ("Listado Precios" and "Listado DAI") and the
// CompanySelector, orchestrates the S3 upload of both files via fileService,
// and then creates the request via requestService.
//
// Behavior (see design.md "File Upload Flow" and Requirements 2.1, 2.4, 2.5,
// 2.6, 2.7, 4.3, 9.1, 9.2):
//  - Renders the submission form directly (Requirement 2.1). The form itself is
//    the "Crear nueva solicitud" affordance for creating a new request.
//  - Tracks the selected file for each slot, the selected company, per-field
//    validation errors, per-slot upload progress and a global submitting flag.
//  - Enables the "Enviar solicitud" button only when both files are attached
//    and a company is selected (Requirement 2.4).
//  - On submit, validates presence of both files and the company; on any
//    missing field it shows an inline Spanish error and keeps the form data
//    (Requirements 2.5, 2.6).
//  - Uploads both files to S3 (presigned URL + PUT with progress) and then
//    calls requestService.createRequest. On success it shows a Spanish
//    confirmation message including the returned requestId (Requirements 2.7,
//    4.3). On failure (upload or create) it shows the Spanish error inline and
//    preserves the form data so the User can retry.
//  - All UI text is in Spanish (Requirements 9.1, 9.2).

import { useState } from 'react';
import { FileUpload, type FileType } from './FileUpload';
import { CompanySelector, type Company } from './CompanySelector';
import { getPresignedUrl, uploadFileToS3 } from '../../services/fileService';
import { createRequest } from '../../services/requestService';

/** Per-field validation / error messages (all Spanish). */
interface FieldErrors {
  listadoPrecios?: string;
  dai?: string;
  company?: string;
  /** General submission error not tied to a specific field. */
  form?: string;
}

/** Successful-submission summary shown as a confirmation banner. */
interface SubmissionResult {
  requestId: string;
  message: string;
}

/** Spanish messages used for inline validation of missing fields. */
const MESSAGES = {
  missingListadoPrecios: 'Debe adjuntar el archivo de Listado Precios.',
  missingDai: 'Debe adjuntar el archivo de Listado DAI.',
  missingCompany: 'Debe seleccionar una empresa.',
  genericSubmitError:
    'No se pudo enviar la solicitud. Por favor, inténtelo de nuevo.',
} as const;

/**
 * Request creation form composing the two file-upload slots and the company
 * selector.
 */
export function RequestForm() {
  // Selected files per slot.
  const [listadoPreciosFile, setListadoPreciosFile] = useState<File | null>(
    null,
  );
  const [daiFile, setDaiFile] = useState<File | null>(null);

  // Selected company ("" until the user chooses one).
  const [company, setCompany] = useState<Company | ''>('');

  // Per-field errors (Spanish).
  const [errors, setErrors] = useState<FieldErrors>({});

  // Upload progress per slot (undefined = not uploading).
  const [listadoPreciosProgress, setListadoPreciosProgress] = useState<
    number | undefined
  >(undefined);
  const [daiProgress, setDaiProgress] = useState<number | undefined>(undefined);

  // Global submitting flag: true while uploading files / creating the request.
  const [submitting, setSubmitting] = useState(false);

  // Confirmation banner shown after a successful submission.
  const [result, setResult] = useState<SubmissionResult | null>(null);

  // The form can be submitted only when both files are attached and a company
  // is selected (Requirement 2.4).
  const canSubmit =
    listadoPreciosFile !== null && daiFile !== null && company !== '';

  /** Record a selected file for the given slot and clear its field error. */
  const handleFileSelected = (file: File, fileType: FileType) => {
    // A new selection invalidates any prior confirmation.
    setResult(null);
    if (fileType === 'listado_precios') {
      setListadoPreciosFile(file);
      setErrors((prev) => ({ ...prev, listadoPrecios: undefined }));
    } else {
      setDaiFile(file);
      setErrors((prev) => ({ ...prev, dai: undefined }));
    }
  };

  /** Record the selected company and clear its field error. */
  const handleCompanyChange = (value: Company) => {
    setResult(null);
    setCompany(value);
    setErrors((prev) => ({ ...prev, company: undefined }));
  };

  /**
   * Validate that both files and the company are present. Returns the set of
   * Spanish field errors (empty when valid).
   */
  const validate = (): FieldErrors => {
    const next: FieldErrors = {};
    if (!listadoPreciosFile) {
      next.listadoPrecios = MESSAGES.missingListadoPrecios;
    }
    if (!daiFile) {
      next.dai = MESSAGES.missingDai;
    }
    if (!company) {
      next.company = MESSAGES.missingCompany;
    }
    return next;
  };

  /**
   * Upload a single file: request a presigned URL and PUT the bytes to S3,
   * reporting progress via the provided setter. Returns the resulting S3 key.
   */
  const uploadOne = async (
    file: File,
    fileType: FileType,
    setProgress: (value: number | undefined) => void,
  ): Promise<string> => {
    setProgress(0);
    try {
      const { uploadUrl, s3Key } = await getPresignedUrl(
        file.name,
        file.type || 'application/octet-stream',
        fileType,
      );
      await uploadFileToS3(uploadUrl, file, (percent) => setProgress(percent));
      // Mark the slot as finished (100%) before clearing.
      setProgress(100);
      return s3Key;
    } finally {
      // Clear the progress indicator once the upload settles (success or error).
      setProgress(undefined);
    }
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    // Clear any prior confirmation before re-validating / re-submitting.
    setResult(null);

    // Validate required fields. On any missing field, show inline errors and
    // keep the form data (Requirements 2.5, 2.6).
    const validationErrors = validate();
    if (
      validationErrors.listadoPrecios ||
      validationErrors.dai ||
      validationErrors.company
    ) {
      setErrors(validationErrors);
      return;
    }

    // Narrow the nullable state now that validation has passed.
    if (!listadoPreciosFile || !daiFile || !company) {
      return;
    }

    setErrors({});
    setSubmitting(true);
    try {
      // Upload the Listado Precios file first. If it fails, we stop and show
      // the error without attempting the second upload or creating the request
      // (Requirement 2.7 / design "File Upload Flow").
      let listadoPreciosS3Key: string;
      try {
        listadoPreciosS3Key = await uploadOne(
          listadoPreciosFile,
          'listado_precios',
          setListadoPreciosProgress,
        );
      } catch (err) {
        setErrors({ listadoPrecios: toMessage(err) });
        return;
      }

      // Upload the DAI file.
      let daiS3Key: string;
      try {
        daiS3Key = await uploadOne(daiFile, 'dai', setDaiProgress);
      } catch (err) {
        setErrors({ dai: toMessage(err) });
        return;
      }

      // Both files uploaded: create the request record.
      try {
        const response = await createRequest({
          listadoPreciosS3Key,
          daiS3Key,
          company,
        });
        // Success: show the Spanish confirmation with the returned requestId
        // (Requirements 2.7, 4.3).
        setResult({
          requestId: response.requestId,
          message: response.message,
        });
      } catch (err) {
        // Persistence failed: show the error and preserve the form data
        // (Requirement 4.3 — do not discard user data).
        setErrors({ form: toMessage(err) });
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="request-form" aria-label="Crear nueva solicitud">
      <h2 className="request-form__title">Crear nueva solicitud</h2>

      {result && (
        <div className="request-form__confirmation" role="status">
          <p>{result.message}</p>
          <p>
            Número de solicitud: <strong>{result.requestId}</strong>
          </p>
        </div>
      )}

      <form className="request-form__form" onSubmit={handleSubmit} noValidate>
        <FileUpload
          label="Listado Precios"
          fileType="listado_precios"
          onFileSelected={handleFileSelected}
          error={errors.listadoPrecios}
          progress={listadoPreciosProgress}
        />

        <FileUpload
          label="Listado DAI"
          fileType="dai"
          onFileSelected={handleFileSelected}
          error={errors.dai}
          progress={daiProgress}
        />

        <CompanySelector
          value={company}
          onChange={handleCompanyChange}
          error={errors.company}
        />

        {errors.form && (
          <p className="request-form__error" role="alert">
            {errors.form}
          </p>
        )}

        <button
          type="submit"
          className="request-form__submit"
          disabled={!canSubmit || submitting}
        >
          {submitting ? 'Enviando…' : 'Enviar solicitud'}
        </button>
      </form>
    </section>
  );
}

/**
 * Extract a Spanish, user-facing message from an unknown thrown value. Both
 * fileService (FileServiceError) and requestService (Error) already produce
 * Spanish messages, so we surface `error.message` when available and fall back
 * to a generic Spanish message otherwise.
 */
function toMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return MESSAGES.genericSubmitError;
}

export default RequestForm;
