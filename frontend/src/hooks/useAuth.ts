// hooks/useAuth.ts
//
// Authentication hook para la plataforma Purdy Renting, sobre AWS Amplify v6
// (@aws-amplify/auth). Centraliza la interaccion con Cognito (User Pool NATIVO,
// email + password) para que el resto de la app consuma un estado de auth
// pequeno y declarativo.
//
// Comportamiento:
//  - Al montar, inspecciona la sesion actual de Cognito y deriva el estado
//    (isAuthenticated, user, loading, tokens).
//  - Se suscribe al canal "auth" del Hub de Amplify para reaccionar a
//    signIn / signOut / tokenRefresh sin refresco manual.
//  - signIn(email, password) inicia sesion con formulario propio (sin Hosted
//    UI). Devuelve si se requiere cambio de contrasena (usuario nuevo).
//  - Amplify refresca los tokens automaticamente; fetchAuthSession los renueva
//    de forma transparente antes de expirar.

import { useCallback, useEffect, useState } from 'react';
import {
  getCurrentUser,
  fetchAuthSession,
  signIn as amplifySignIn,
  confirmSignIn as amplifyConfirmSignIn,
  signOut,
  type AuthUser,
  type AuthSession,
} from 'aws-amplify/auth';
import { Hub } from 'aws-amplify/utils';

/** Shape of the authentication state exposed by {@link useAuth}. */
export interface AuthState {
  /** True once a valid Cognito session with an access token is established. */
  isAuthenticated: boolean;
  /** The current Cognito user, or null when unauthenticated. */
  user: AuthUser | null;
  /** The current Cognito session (tokens/credentials), or null when unauthenticated. */
  session: AuthSession | null;
  /** True while the initial session check (or a refresh) is in progress. */
  loading: boolean;
}

/** Resultado de un intento de inicio de sesion. */
export interface SignInResult {
  /** True si el inicio de sesion se completo y hay sesion valida. */
  isSignedIn: boolean;
  /**
   * True si Cognito requiere que el usuario establezca una nueva contrasena
   * (paso NEW_PASSWORD_REQUIRED, tipico en usuarios creados por el admin).
   */
  requiresNewPassword: boolean;
}

/** Public API returned by {@link useAuth}. */
export interface UseAuthResult extends AuthState {
  /** Inicia sesion con email + password (formulario propio). */
  signIn: (email: string, password: string) => Promise<SignInResult>;
  /** Completa el reto NEW_PASSWORD_REQUIRED con la nueva contrasena. */
  completeNewPassword: (newPassword: string) => Promise<SignInResult>;
  /** Cierra la sesion de Cognito. */
  logout: () => Promise<void>;
  /** Re-lee la sesion actual (fuerza refresco de tokens). */
  refreshSession: () => Promise<AuthSession | null>;
}

const INITIAL_STATE: AuthState = {
  isAuthenticated: false,
  user: null,
  session: null,
  loading: true,
};

export function useAuth(): UseAuthResult {
  const [state, setState] = useState<AuthState>(INITIAL_STATE);

  /**
   * Carga el estado de autenticacion actual desde Amplify.
   *
   * `fetchAuthSession` devuelve la sesion cacheada y refresca tokens de forma
   * transparente cuando estan cerca de expirar. Una sesion sin access token
   * significa que no hay login valido -> se trata como no autenticado.
   */
  const loadSession = useCallback(
    async (forceRefresh = false): Promise<AuthSession | null> => {
      try {
        const session = await fetchAuthSession({ forceRefresh });
        const hasValidToken = Boolean(session.tokens?.accessToken);

        if (!hasValidToken) {
          setState({
            isAuthenticated: false,
            user: null,
            session: null,
            loading: false,
          });
          return null;
        }

        let user: AuthUser | null = null;
        try {
          user = await getCurrentUser();
        } catch {
          setState({
            isAuthenticated: false,
            user: null,
            session: null,
            loading: false,
          });
          return null;
        }

        setState({
          isAuthenticated: true,
          user,
          session,
          loading: false,
        });
        return session;
      } catch {
        setState({
          isAuthenticated: false,
          user: null,
          session: null,
          loading: false,
        });
        return null;
      }
    },
    [],
  );

  // Chequeo inicial + suscripcion a eventos de auth.
  useEffect(() => {
    let active = true;

    void loadSession();

    const unsubscribe = Hub.listen('auth', ({ payload }) => {
      if (!active) return;

      switch (payload.event) {
        case 'signedIn':
        case 'tokenRefresh':
          void loadSession();
          break;
        case 'signedOut':
          setState({
            isAuthenticated: false,
            user: null,
            session: null,
            loading: false,
          });
          break;
        case 'tokenRefresh_failure':
          setState({
            isAuthenticated: false,
            user: null,
            session: null,
            loading: false,
          });
          break;
        default:
          break;
      }
    });

    return () => {
      active = false;
      unsubscribe();
    };
  }, [loadSession]);

  /** Inicia sesion con email + password. */
  const signIn = useCallback(
    async (email: string, password: string): Promise<SignInResult> => {
      const { isSignedIn, nextStep } = await amplifySignIn({
        username: email,
        password,
      });

      if (isSignedIn) {
        await loadSession(true);
        return { isSignedIn: true, requiresNewPassword: false };
      }

      const requiresNewPassword =
        nextStep?.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED';

      return { isSignedIn: false, requiresNewPassword };
    },
    [loadSession],
  );

  /** Completa el reto de nueva contrasena (usuario recien creado). */
  const completeNewPassword = useCallback(
    async (newPassword: string): Promise<SignInResult> => {
      const { isSignedIn } = await amplifyConfirmSignIn({
        challengeResponse: newPassword,
      });

      if (isSignedIn) {
        await loadSession(true);
        return { isSignedIn: true, requiresNewPassword: false };
      }
      return { isSignedIn: false, requiresNewPassword: false };
    },
    [loadSession],
  );

  /** Cierra sesion y limpia el estado local. */
  const logout = useCallback(async (): Promise<void> => {
    await signOut();
    setState({
      isAuthenticated: false,
      user: null,
      session: null,
      loading: false,
    });
  }, []);

  /** Fuerza re-evaluacion de la sesion y refresco de tokens. */
  const refreshSession = useCallback(
    (): Promise<AuthSession | null> => loadSession(true),
    [loadSession],
  );

  return {
    ...state,
    signIn,
    completeNewPassword,
    logout,
    refreshSession,
  };
}

export default useAuth;
