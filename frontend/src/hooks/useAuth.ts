// hooks/useAuth.ts
//
// Authentication hook for the Purdy Renting platform, built on AWS Amplify v6
// (@aws-amplify/auth). It centralizes all interaction with Cognito so the rest
// of the app can consume a small, declarative auth state.
//
// Behavior (see design.md "Authentication Flow" and Requirements 1.1, 1.2,
// 1.4, 1.6):
//  - On mount, it inspects the current Cognito session and derives the
//    authentication state (isAuthenticated, user, loading, tokens).
//  - It subscribes to Amplify's Hub "auth" channel so sign-in / sign-out /
//    token-refresh events (including those triggered by returning from the
//    Hosted UI redirect) update state without a manual refresh.
//  - login() starts the Cognito Hosted UI flow via signInWithRedirect, which
//    federates to Microsoft Entra ID (Requirement 1.1).
//  - Token refresh is handled by Amplify: fetchAuthSession transparently uses
//    the refresh token to renew Access/ID tokens before expiry. This hook
//    exposes the current session/tokens and re-fetches on token-refresh events
//    (Requirement 1.2).
//  - When the session can no longer be established (refresh token expired /
//    revoked), the hook marks the user unauthenticated so callers such as
//    ProtectedRoute can trigger re-authentication (Requirements 1.4, 1.6).

import { useCallback, useEffect, useState } from 'react';
import {
  getCurrentUser,
  fetchAuthSession,
  signInWithRedirect,
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

/** Public API returned by {@link useAuth}. */
export interface UseAuthResult extends AuthState {
  /** Start the Cognito Hosted UI login flow (redirects to Entra ID). */
  login: () => Promise<void>;
  /** Sign the user out of Cognito (clears the session). */
  logout: () => Promise<void>;
  /**
   * Re-read the current session from Amplify. Amplify refreshes tokens
   * automatically when needed; call this to force a re-evaluation (e.g. after
   * a 401 from the API) and to obtain fresh tokens.
   */
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
   * Load the current authentication state from Amplify.
   *
   * `fetchAuthSession` returns the cached session and transparently refreshes
   * the Access/ID tokens using the refresh token when they are close to
   * expiry (or when `forceRefresh` is requested). A session without an access
   * token means there is no valid login, which we surface as unauthenticated
   * so the app can redirect to the Hosted UI (Requirements 1.4, 1.6).
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

        // A valid session exists; resolve the user identity as well.
        let user: AuthUser | null = null;
        try {
          user = await getCurrentUser();
        } catch {
          // Session tokens present but user lookup failed; treat as
          // unauthenticated rather than a partially-authenticated state.
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
        // No session, expired refresh token, or a transient error. Callers
        // treat this as "needs authentication".
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

  // Initial session check on mount + subscription to Amplify auth events.
  useEffect(() => {
    let active = true;

    // Evaluate the session once when the hook first mounts.
    void loadSession();

    // React to auth lifecycle events. Amplify emits these on the "auth"
    // channel for sign-in (including Hosted UI redirect completion), sign-out,
    // token refresh, and session expiry.
    const unsubscribe = Hub.listen('auth', ({ payload }) => {
      if (!active) return;

      switch (payload.event) {
        case 'signedIn':
        case 'signInWithRedirect':
        case 'tokenRefresh':
          // New or refreshed tokens available; re-read the session.
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
        case 'signInWithRedirect_failure':
          // The session could not be renewed/established; force re-auth.
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

  /** Redirect to the Cognito Hosted UI (which federates to Entra ID). */
  const login = useCallback(async (): Promise<void> => {
    await signInWithRedirect();
  }, []);

  /** Sign out of Cognito and clear local session state. */
  const logout = useCallback(async (): Promise<void> => {
    await signOut();
    setState({
      isAuthenticated: false,
      user: null,
      session: null,
      loading: false,
    });
  }, []);

  /** Force a session re-evaluation and token refresh. */
  const refreshSession = useCallback(
    (): Promise<AuthSession | null> => loadSession(true),
    [loadSession],
  );

  return {
    ...state,
    login,
    logout,
    refreshSession,
  };
}

export default useAuth;
