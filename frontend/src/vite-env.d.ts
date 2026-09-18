/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Cognito User Pool ID, e.g. "us-east-1_ABC123". */
  readonly VITE_COGNITO_USER_POOL_ID?: string;
  /** Cognito App Client ID (User Pool client). */
  readonly VITE_COGNITO_USER_POOL_CLIENT_ID?: string;
  /** AWS region hosting the Cognito User Pool, e.g. "us-east-1". */
  readonly VITE_AWS_REGION?: string;
  /**
   * Base URL of the backend API Gateway, e.g. "https://api.example.com".
   * Set this to the SAM stack output `ApiBaseUrl` to point the frontend at a
   * deployed backend. Consumed by the shared axios client in `src/config/api.ts`.
   */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
