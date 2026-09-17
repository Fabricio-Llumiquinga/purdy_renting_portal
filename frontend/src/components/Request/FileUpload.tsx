// components/Request/FileUpload.tsx
//
// Presentational file-attachment field for a single upload slot of the request
// form (either "Listado Precios" or "Listado DAI").
//
// Behavior (see design.md "FileUpload" and Requirements 2.2, 2.5, 2.8, 3.4,
// 3.5, 9.1, 9.2):
//  - Accepts only .xls, .xlsx and .csv files via the native file picker
//    `accept` attribute AND enforces the same rule with a case-insensitive
//    extension check on selection (Requirements 2.2, 2.8, 3.5).
//  - Rejects files larger than 10 MB, showing a Spanish size error
//    (Requirements 2.8, 3.4).
//  - Shows validation errors inline in Spanish, both from internal validation
//    and from the parent-supplied `error` prop (Requirements 2.5, 2.8, 9.1).
//  - Displays the selected file name and, while uploading, an upload progress
//    indicator driven by the optional `progress` prop (Requirement 3.4, 9.2).
//  - Allows cancelling an in-progress upload via the optional `onCancel`
//    callback, exposed as a "Cancelar" button while uploading.
//
// This component is intentionally presentational + validation only. The actual
// S3 upload is orchestrated by the parent RequestForm together with
// fileService (task 9.4); this component never calls fileService directly.

import { useId, useState } from 'react';
import type { PresignedUrlRequest } from '../../types';

/** Logical upload slot. Mirrors PresignedUrlRequest["fileType"]. */
export type FileType = PresignedUrlRequest['fileType'];

/** Allowed file extensions (lower-case, including the leading dot). */
export const ALLOWED_EXTENSIONS = ['.xls', '.xlsx', '.csv'] as const;

/** `accept` attribute value for the native file input. */
const ACCEPT_ATTR = ALLOWED_EXTENSIONS.join(',');

/** Maximum allowed file size in bytes (10 MB). */
export const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;

/** Human-readable size limit used in Spanish error messages. */
const MAX_FILE_SIZE_LABEL = '10 MB';

export interface FileUploadProps {
  /** Field label shown to the user (already in Spanish), e.g. "Listado Precios". */
  label: string;
  /** Logical upload slot this field represents. */
  fileType: FileType;
  /**
   * Invoked with the selected File when it passes extension and size
   * validation. The parent uses this to orchestrate the S3 upload.
   */
  onFileSelected: (file: File, fileType: FileType) => void;
  /**
   * Optional inline validation/upload error message from the parent (already
   * in Spanish). Displayed in addition to internal validation messages.
   */
  error?: string;
  /**
   * Optional upload progress percentage (0–100). When provided and between
   * 0 and 100 (inclusive of 0, exclusive of 100 for the "uploading" state),
   * a progress indicator is shown. When undefined, no progress is shown.
   */
  progress?: number;
  /**
   * Optional callback to cancel an in-progress upload. When provided together
   * with an active upload, a "Cancelar" button is rendered.
   */
  onCancel?: () => void;
}

/**
 * Validate a file's extension against the allowed set (case-insensitive).
 * Returns a Spanish error message when invalid, or null when valid.
 */
export function validateFileExtension(fileName: string): string | null {
  const lower = fileName.toLowerCase();
  const isAllowed = ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext));
  if (!isAllowed) {
    return 'Formato de archivo no válido. Solo se permiten archivos .xls, .xlsx o .csv.';
  }
  return null;
}

/**
 * Validate a file's size against the 10 MB limit.
 * Returns a Spanish error message when too large, or null when valid.
 */
export function validateFileSize(sizeBytes: number): string | null {
  if (sizeBytes > MAX_FILE_SIZE_BYTES) {
    return `El archivo excede el tamaño máximo permitido de ${MAX_FILE_SIZE_LABEL}.`;
  }
  return null;
}

/**
 * Single-file attachment field with extension/size validation, selected-file
 * display, upload progress and cancel support.
 */
export function FileUpload({
  label,
  fileType,
  onFileSelected,
  error,
  progress,
  onCancel,
}: FileUploadProps) {
  const inputId = useId();
  const errorId = `${inputId}-error`;

  // Name of the currently selected (and valid) file, for display.
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  // Internal validation error message (Spanish) for the last selection.
  const [validationError, setValidationError] = useState<string | null>(null);

  // An upload is considered "in progress" when a numeric progress in the
  // range [0, 100) is provided by the parent.
  const isUploading =
    typeof progress === 'number' && progress >= 0 && progress < 100;

  // Prefer the parent-supplied error, otherwise fall back to internal
  // validation feedback. Both are already in Spanish.
  const displayedError = error ?? validationError ?? undefined;
  const hasError = Boolean(displayedError);

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];

    if (!file) {
      // Selection cleared (e.g. user cancelled the OS file dialog).
      setSelectedFileName(null);
      setValidationError(null);
      return;
    }

    const extensionError = validateFileExtension(file.name);
    if (extensionError) {
      setSelectedFileName(null);
      setValidationError(extensionError);
      // Reset the input so re-selecting the same file re-triggers onChange.
      event.target.value = '';
      return;
    }

    const sizeError = validateFileSize(file.size);
    if (sizeError) {
      setSelectedFileName(null);
      setValidationError(sizeError);
      event.target.value = '';
      return;
    }

    // Valid file: clear internal error, record name, notify parent.
    setValidationError(null);
    setSelectedFileName(file.name);
    onFileSelected(file, fileType);
  };

  const progressValue = isUploading ? Math.round(progress as number) : 0;

  return (
    <div className="file-upload">
      <label htmlFor={inputId} className="file-upload__label">
        {label}
      </label>

      <input
        id={inputId}
        type="file"
        accept={ACCEPT_ATTR}
        onChange={handleChange}
        disabled={isUploading}
        aria-invalid={hasError || undefined}
        aria-describedby={hasError ? errorId : undefined}
        className="file-upload__input"
      />

      {selectedFileName && (
        <p className="file-upload__filename">
          Archivo seleccionado: {selectedFileName}
        </p>
      )}

      {isUploading && (
        <div className="file-upload__progress">
          <progress
            className="file-upload__progress-bar"
            max={100}
            value={progressValue}
            aria-label={`Progreso de carga: ${progressValue}%`}
          />
          <span className="file-upload__progress-text">{progressValue}%</span>
          {onCancel && (
            <button
              type="button"
              className="file-upload__cancel"
              onClick={onCancel}
            >
              Cancelar
            </button>
          )}
        </div>
      )}

      {hasError && (
        <p id={errorId} role="alert" className="file-upload__error">
          {displayedError}
        </p>
      )}
    </div>
  );
}

export default FileUpload;
