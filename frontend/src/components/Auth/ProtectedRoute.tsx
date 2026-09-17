// components/Auth/ProtectedRoute.tsx
//
// Route guard that only renders its children for authenticated users. It relies
// on the useAuth hook for the current authentication state.
//
// En modo demo (SKIP_AUTH) se omite el login y se renderizan directamente
// los hijos, para permitir la vista previa local sin Cognito.

import { useEffect, type ReactNode } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { SKIP_AUTH } from '../../config/demo';

export interface ProtectedRouteProps {
  /** The protected content to render once the user is authenticated. */
  children: ReactNode;
  fallback?: ReactNode;
}

/**
 * Guards a route/subtree: renders `children` only when authenticated,
 * otherwise triggers the login redirect. En modo demo siempre renderiza.
 */
export function ProtectedRoute({ children, fallback }: ProtectedRouteProps) {
  const { isAuthenticated, loading, login } = useAuth();

  useEffect(() => {
    if (SKIP_AUTH) return;
    if (!loading && !isAuthenticated) {
      void login();
    }
  }, [loading, isAuthenticated, login]);

  // En modo demo se omite por completo el flujo de autenticacion.
  if (SKIP_AUTH) {
    return <>{children}</>;
  }

  if (loading) {
    return <>{fallback ?? <div role="status">Cargando&hellip;</div>}</>;
  }

  if (!isAuthenticated) {
    return <>{fallback ?? <div role="status">Redirigiendo al inicio de sesi&oacute;n&hellip;</div>}</>;
  }

  return <>{children}</>;
}

export default ProtectedRoute;
