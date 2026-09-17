// types/index.ts
// Shared TypeScript interfaces for the Purdy Renting Platform frontend.
// Definitions mirror the API contracts described in design.md.

export interface Request {
  requestId: string;
  userEmail: string;
  company: "Purdy Motor" | "Automotriz";
  companyCode: "PM" | "AUTO";
  listadoPreciosS3Key: string;
  daiS3Key: string;
  generatedFileName: string | null;
  generatedFileS3Key: string | null;
  status: "Pendiente de Procesar" | "Procesando" | "Procesado" | "Failed";
  observation: string | null;
  createdAt: string; // ISO 8601
  updatedAt: string; // ISO 8601
}

export interface CreateRequestPayload {
  listadoPreciosS3Key: string;
  daiS3Key: string;
  company: "Purdy Motor" | "Automotriz";
}

export interface PresignedUrlRequest {
  fileName: string;
  contentType: string;
  fileType: "listado_precios" | "dai";
}

export interface PresignedUrlResponse {
  uploadUrl: string;
  s3Key: string;
}

export interface CreateRequestResponse {
  requestId: string;
  message: string;
}
