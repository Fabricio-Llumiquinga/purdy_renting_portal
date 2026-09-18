// config/api.ts
//
// Shared axios API client for the Purdy Renting platform frontend.
//
// This is the single, canonical axios instance used by every service that
// talks to the backend API Gateway (see design.md "API Gateway Routes"). It
// centralises three concerns that were previously duplicated across services:
//
//   1. Base URL — read once from `import.meta.env.VITE_API_BASE_URL` so the
//      same build can target different environments (dev / staging / prod).
//   2. Auth token injection (Requirement 1.5) — a request interceptor attaches
//      the current Cognito Access token as `Authorization: Bearer <token>` on
//      every outgoing request, obtained from Amplify Auth via
//      `fetchAuthSession` (which transparently refreshes tokens near expiry).
//   3. Session-expiry handling (Requirements 1.4, 1.6) — a response interceptor
//      detects HTTP 401 responses and signals that the session is no longer
//      valid so the app can redirect the User to the login page.
//
// IMPORTANT: This client is only for backend API Gateway calls. Direct-to-S3
// requests (e.g. the presigned PUT upload in fileService) MUST NOT use this
// client — the presigned URL already carries signed credentials, and an extra
// `Authorization` header (or an inherited baseURL) would cause S3 to reject the
// request. Those calls continue to use a bare `axios` instance.
//
// CORS: Cross-origin access is configured on API Gateway in the SAM template
// (task 13.2). No frontend code change is required for CORS beyond pointing
// `VITE_API_BASE_URL` at the deployed API base URL.
import axios, { type AxiosInstance } from 'axios';
import { fetchAuthSession } from 'aws-amplify/auth';

/**
 * Base URL of the API Gateway stage. Read from Vite env so the same build can
 * target different environments. Trailing slashes are trimmed so that relative
 * request paths (e.g. `/requests`) join predictably. A localhost fallback keeps
 * the app compiling and runnable before real infrastructure exists.
 *
 * To point the app at a deployed backend, set `VITE_API_BASE_URL` to the SAM
 * stack output `ApiBaseUrl` (see verification notes below / vite-env.d.ts).
 */
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, '') ?? 'http://localhost:3000';

/**
 * Name of the DOM event dispatched when a 401 is observed. The app (or an auth
 * provider) can listen for this to trigger a redirect to the login page
 * without this low-level module needing to know about routing.
 *
 * Example listener:
 *   window.addEventListener(SESSION_EXPIRED_EVENT, () => navigate('/login'));
 */
export const SESSION_EXPIRED_EVENT = 'auth:session-expired';

/**
 * The shared, authenticated API client. Use this for all backend API Gateway
 * calls. Do NOT use it for direct-to-S3 requests.
 */
export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

/**
 * Request interceptor: attach the Cognito Access token to every outgoing
 * request (Requirement 1.5).
 *
 * `fetchAuthSession` returns the current session, refreshing tokens
 * transparently when needed. If no token is available (e.g. unauthenticated),
 * the request proceeds without the header and the backend responds 401, which
 * is handled by the response interceptor below.
 */
apiClient.interceptors.request.use(async (config) => {
  try {
    const session = await fetchAuthSession();
    // Usar el ID token: el authorizer Cognito y el backend leen claims como
    // "email"/"name", que SOLO estan presentes en el ID token (el access token
    // de Cognito no incluye esos atributos de perfil).
    const idToken = session.tokens?.idToken?.toString();
    if (idToken) {
      config.headers.Authorization = `Bearer ${idToken}`;
    }
  } catch {
    // No valid session; let the request proceed and let the backend reject it.
  }
  return config;
});

/**
 * Response interceptor: on a 401, signal that the session has expired
 * (Requirements 1.4, 1.6).
 *
 * Kept intentionally minimal and non-breaking:
 *   - It dispatches a `SESSION_EXPIRED_EVENT` on `window` so the app can react
 *     (e.g. redirect to login) without coupling this module to the router.
 *   - It always re-rejects the original error so existing per-call error
 *     handling (e.g. Spanish error mapping in the services) is unchanged.
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      // Notify listeners that the session is no longer valid. Guarded so the
      // module stays safe in non-browser (e.g. test/SSR) environments.
      if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
        window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
      }
    }
    return Promise.reject(error);
  },
);

export default apiClient;
