// services/fileService.ts
// File upload service.
//
//  - Demo (IS_DEMO_MODE): simula todo en el navegador.
//  - Local (IS_LOCAL_MODE): llama al backend local real, SIN token Cognito.
//  - Produccion: backend real con token Cognito.

import axios, { AxiosError } from "axios";
import { fetchAuthSession } from "aws-amplify/auth";
import { apiClient } from "../config/api";
import type { PresignedUrlRequest, PresignedUrlResponse } from "../types";
import { IS_DEMO_MODE, IS_LOCAL_MODE } from "../config/demo";

export class FileServiceError extends Error {
  readonly status?: number;
  readonly cause?: unknown;
  constructor(message: string, options?: { status?: number; cause?: unknown }) {
    super(message);
    this.name = "FileServiceError";
    this.status = options?.status;
    this.cause = options?.cause;
  }
}

export type UploadProgressCallback = (percentComplete: number) => void;

async function getAccessToken(): Promise<string | null> {
  // En modo local no hay Cognito: se envia sin token.
  if (IS_LOCAL_MODE) return null;
  try {
    const session = await fetchAuthSession();
    // ID token: contiene los claims email/name que exige el backend.
    const token = session.tokens?.idToken?.toString();
    if (!token) {
      throw new FileServiceError("No hay una sesion activa. Inicie sesion nuevamente.", { status: 401 });
    }
    return token;
  } catch (error) {
    if (error instanceof FileServiceError) throw error;
    throw new FileServiceError("No se pudo obtener la sesion de autenticacion.", { status: 401, cause: error });
  }
}

export async function getPresignedUrl(
  fileName: string,
  contentType: string,
  fileType: PresignedUrlRequest["fileType"]
): Promise<PresignedUrlResponse> {
  if (IS_DEMO_MODE) {
    return { uploadUrl: "https://demo.local/upload", s3Key: `uploads/demo/${fileType}_${fileName}` };
  }

  const token = await getAccessToken();
  const payload: PresignedUrlRequest = { fileName, contentType, fileType };
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const response = await apiClient.post<PresignedUrlResponse>(
      "/requests/presigned-url", payload, { headers }
    );
    return response.data;
  } catch (error) {
    throw toFileServiceError(error, "No se pudo generar la URL de carga del archivo.");
  }
}

export async function uploadFileToS3(
  presignedUrl: string,
  file: File | Blob,
  onProgress?: UploadProgressCallback
): Promise<void> {
  if (IS_DEMO_MODE) {
    for (let p = 20; p <= 100; p += 20) {
      await new Promise((r) => setTimeout(r, 120));
      onProgress?.(p);
    }
    return;
  }

  try {
    // El presignedUrl puede ser el backend local (/local-upload/...) o S3 real.
    // En ambos casos es un PUT directo con el binario, sin auth header.
    await axios.put(presignedUrl, file, {
      headers: { "Content-Type": file.type || "application/octet-stream" },
      transformRequest: [(data) => data],
      onUploadProgress: (progressEvent) => {
        if (!onProgress) return;
        const total = progressEvent.total ?? 0;
        if (total > 0) {
          const percent = Math.round((progressEvent.loaded * 100) / total);
          onProgress(Math.min(100, Math.max(0, percent)));
        }
      },
    });
  } catch (error) {
    throw toFileServiceError(error, "No se pudo cargar el archivo. Intente nuevamente.");
  }
}

function toFileServiceError(error: unknown, fallbackMessage: string): FileServiceError {
  if (error instanceof FileServiceError) return error;
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{ message?: string }>;
    const status = axiosError.response?.status;
    const serverMessage = axiosError.response?.data?.message;
    return new FileServiceError(serverMessage ?? fallbackMessage, { status, cause: error });
  }
  return new FileServiceError(fallbackMessage, { cause: error });
}