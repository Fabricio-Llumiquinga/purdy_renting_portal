// services/requestService.ts
//
//  - Demo (IS_DEMO_MODE): createRequest/getDownloadUrl simulados.
//  - Local (IS_LOCAL_MODE) / Produccion: backend real.

import axios, { AxiosError } from 'axios';
import { apiClient } from '../config/api';
import type { CreateRequestPayload, CreateRequestResponse, Request } from '../types';
import { IS_DEMO_MODE } from '../config/demo';

export interface DownloadUrlResponse {
  downloadUrl: string;
  fileName: string;
}

interface ApiErrorBody { error?: { code?: string; message?: string }; }

const FALLBACK_ERROR_MESSAGE = 'Ocurrio un error inesperado. Por favor, intentelo de nuevo.';
const NETWORK_ERROR_MESSAGE = 'No se pudo conectar con el servidor. Verifique su conexion e intentelo de nuevo.';

function toSpanishError(err: unknown): Error {
  if (axios.isAxiosError(err)) {
    const axiosErr = err as AxiosError<ApiErrorBody>;
    const backendMessage = axiosErr.response?.data?.error?.message;
    if (backendMessage) return new Error(backendMessage);
    if (!axiosErr.response) return new Error(NETWORK_ERROR_MESSAGE);
    return new Error(FALLBACK_ERROR_MESSAGE);
  }
  return new Error(FALLBACK_ERROR_MESSAGE);
}

export async function createRequest(payload: CreateRequestPayload): Promise<CreateRequestResponse> {
  if (IS_DEMO_MODE) {
    await new Promise((r) => setTimeout(r, 300));
    const requestId = `demo-${Math.random().toString(36).slice(2, 8)}`;
    return { requestId, message: `Solicitud creada (demo) para ${payload.company}. Estado: Pendiente de Procesar.` };
  }
  try {
    const response = await apiClient.post<CreateRequestResponse>('/requests', payload);
    return response.data;
  } catch (err) {
    throw toSpanishError(err);
  }
}

export async function getRequests(): Promise<Request[]> {
  try {
    // El backend responde { requests: [...] }. Extraemos el array y toleramos
    // que venga como arreglo directo por robustez.
    const response = await apiClient.get<{ requests?: Request[] } | Request[]>('/requests');
    const data = response.data;
    if (Array.isArray(data)) return data;
    return data?.requests ?? [];
  } catch (err) {
    throw toSpanishError(err);
  }
}

export async function getDownloadUrl(requestId: string): Promise<DownloadUrlResponse> {
  if (IS_DEMO_MODE) {
    return { downloadUrl: '#', fileName: 'archivo-demo.xlsx' };
  }
  try {
    const response = await apiClient.get<DownloadUrlResponse>(
      `/requests/${encodeURIComponent(requestId)}/download`,
    );
    return response.data;
  } catch (err) {
    throw toSpanishError(err);
  }
}

export default { createRequest, getRequests, getDownloadUrl };