/**
 * AWS Amplify (v6) authentication configuration for the Purdy Renting platform.
 *
 * Authentication model (see design.md "Authentication Flow" and
 * "Cognito User Pool Configuration"):
 *  - AWS Cognito User Pool acts as an OIDC bridge that federates identity to
 *    Microsoft Entra ID. The React SPA never talks to Entra ID directly; it
 *    uses the Cognito Hosted UI, which redirects to Entra ID for corporate
 *    sign-in and returns standard Cognito JWTs (ID / Access / Refresh).
 *  - The Access token is sent on every API Gateway call and validated by the
 *    Cognito Authorizer (Requirements 1.2, 1.5).
 *
 * Token lifetimes (managed by Cognito, not configured on the client):
 *  - ID and Access tokens: 60 minutes.
 *  - Refresh token: 30 days.
 * Amplify Auth automatically uses the refresh token to obtain new Access/ID
 * tokens before expiry, so the client does not need to schedule refreshes
 * manually. Session expiration (refresh token expired) surfaces as a failed
 * `fetchAuthSession`, which the app handles by redirecting to login
 * (Requirements 1.4, 1.6).
 *
 * Configuration values are read from Vite environment variables
 * (`import.meta.env.VITE_*`) so that the same build can target different
 * environments. Placeholder fallbacks are provided so the app compiles and
 * runs in local development before real infrastructure exists; replace them
 * via a `.env` file / deployment pipeline for real environments.
 */
import { Amplify } from 'aws-amplify';
import type { ResourcesConfig } from 'aws-amplify';

const env = import.meta.env;

/** Cognito Hosted UI domain (host only, no protocol). */
const cognitoDomain =
  env.VITE_COGNITO_DOMAIN ??
  'purdy-renting.auth.us-east-1.amazoncognito.com';

/** OAuth callback URL registered in Cognito. Design default: https://{domain}/callback */
const redirectSignIn =
  env.VITE_COGNITO_REDIRECT_SIGN_IN ?? 'http://localhost:5173/callback';

/** OAuth logout URL registered in Cognito. Design default: https://{domain}/login */
const redirectSignOut =
  env.VITE_COGNITO_REDIRECT_SIGN_OUT ?? 'http://localhost:5173/login';

/** Name of the Entra ID OIDC identity provider as configured in the User Pool. */
const entraProviderName =
  env.VITE_COGNITO_ENTRA_PROVIDER_NAME ?? 'MicrosoftEntraID';

/**
 * The Amplify v6 auth configuration object.
 *
 * `loginWith.oauth` wires the Hosted UI to the OIDC flow. The
 * `authorization_code` (PKCE) grant is used via `responseType: 'code'`, which
 * is the recommended grant for SPAs. Entra ID is exposed through Cognito as a
 * custom OIDC provider, referenced by name in `providers`.
 */
export const authConfig: ResourcesConfig['Auth'] = {
  Cognito: {
    userPoolId: env.VITE_COGNITO_USER_POOL_ID ?? 'us-east-1_XXXXXXXXX',
    userPoolClientId:
      env.VITE_COGNITO_USER_POOL_CLIENT_ID ?? 'xxxxxxxxxxxxxxxxxxxxxxxxxx',
    loginWith: {
      oauth: {
        domain: cognitoDomain,
        // Standard OIDC scopes: identify the user (openid) and read profile/email.
        scopes: ['email', 'openid', 'profile'],
        redirectSignIn: [redirectSignIn],
        redirectSignOut: [redirectSignOut],
        // Authorization Code grant with PKCE (recommended for SPAs).
        responseType: 'code',
        // Federate to the Microsoft Entra ID OIDC provider configured in Cognito.
        providers: [{ custom: entraProviderName }],
      },
    },
  },
};

/** The full Amplify configuration object passed to `Amplify.configure`. */
export const amplifyConfig: ResourcesConfig = {
  Auth: authConfig,
};

/**
 * Configure Amplify with the Cognito/Entra ID auth settings.
 *
 * Call once during application bootstrap (e.g. in `main.tsx`) before any
 * authentication or API calls are made.
 */
export function configureAmplify(): void {
  Amplify.configure(amplifyConfig);
}

export default amplifyConfig;
