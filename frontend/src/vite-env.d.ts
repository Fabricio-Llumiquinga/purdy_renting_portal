/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Cognito User Pool ID, e.g. "us-east-1_ABC123". */
  readonly VITE_COGNITO_USER_POOL_ID?: string;
  /** Cognito App Client ID (User Pool client). */
  readonly VITE_COGNITO_USER_POOL_CLIENT_ID?: string;
  /** Cognito Hosted UI domain, without protocol, e.g. "purdy-renting.auth.us-east-1.amazoncognito.com". */
  readonly VITE_COGNITO_DOMAIN?: string;
  /** OAuth callback URL registered in Cognito, e.g. "https://app.example.com/callback". */
  readonly VITE_COGNITO_REDIRECT_SIGN_IN?: string;
  /** OAuth logout URL registered in Cognito, e.g. "https://app.example.com/login". */
  readonly VITE_COGNITO_REDIRECT_SIGN_OUT?: string;
  /** Name of the Entra ID OIDC provider as configured in Cognito, e.g. "MicrosoftEntraID". */
  readonly VITE_COGNITO_ENTRA_PROVIDER_NAME?: string;
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
