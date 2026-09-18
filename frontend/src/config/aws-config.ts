/**
 * AWS Amplify (v6) authentication configuration for the Purdy Renting platform.
 *
 * Modelo de autenticacion: Cognito User Pool NATIVO (email + password). Los
 * usuarios los da de alta un administrador (AllowAdminCreateUserOnly) y el SPA
 * administra su propio formulario de login (sin Hosted UI ni federacion
 * externa). Amplify se usa solo como cliente de Cognito para signIn/signOut,
 * gestion de sesion y refresco automatico de tokens.
 *
 * El Access token se envia en cada llamada a API Gateway y lo valida el
 * Cognito Authorizer (Requirements 1.2, 1.5).
 *
 * Token lifetimes (gestionados por Cognito):
 *  - ID / Access tokens: 60 minutos.
 *  - Refresh token: 30 dias.
 * Amplify renueva los tokens automaticamente antes de expirar.
 *
 * Los valores se leen de variables de entorno Vite (`import.meta.env.VITE_*`)
 * para que el mismo build sirva a distintos entornos.
 */
import { Amplify } from 'aws-amplify';
import type { ResourcesConfig } from 'aws-amplify';

const env = import.meta.env;

/**
 * Configuracion Amplify v6 para Cognito nativo.
 *
 * `loginWith.email: true` habilita el inicio de sesion con email + password
 * usando el flujo USER_SRP_AUTH (por defecto en Amplify v6). No se define
 * `oauth` porque no usamos Hosted UI.
 */
export const authConfig: ResourcesConfig['Auth'] = {
  Cognito: {
    userPoolId: env.VITE_COGNITO_USER_POOL_ID ?? 'us-east-1_XXXXXXXXX',
    userPoolClientId:
      env.VITE_COGNITO_USER_POOL_CLIENT_ID ?? 'xxxxxxxxxxxxxxxxxxxxxxxxxx',
    loginWith: {
      email: true,
    },
  },
};

/** The full Amplify configuration object passed to `Amplify.configure`. */
export const amplifyConfig: ResourcesConfig = {
  Auth: authConfig,
};

/**
 * Configure Amplify with the Cognito auth settings.
 *
 * Call once during application bootstrap (e.g. in `main.tsx`) before any
 * authentication or API calls are made.
 */
export function configureAmplify(): void {
  Amplify.configure(amplifyConfig);
}

export default amplifyConfig;
