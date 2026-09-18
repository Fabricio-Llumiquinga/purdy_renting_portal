// components/Auth/ProtectedRoute.tsx
//
// Route guard que solo renderiza sus hijos para usuarios autenticados. Usa el
// hook useAuth para el estado actual. Si no hay sesion, redirige a /login
// (formulario propio, Cognito nativo), conservando la ruta de origen para
// volver a ella tras el login.
//
// En modo demo (SKIP_AUTH) se omite el login y se renderizan directamente los
// hijos, para permitir la vista previa local sin Cognito.

import { type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { SKIP_AUTH } from '../../config/demo';

export interface ProtectedRouteProps {
  /** The protected content to render once the user is authenticated. */
  children: ReactNode;
  fallback?: ReactNode;
}

/**
 * Guarda una ruta/subarbol: renderiza `children` solo si esta autenticado;
 * de lo contrario redirige a /login. En modo demo siempre renderiza.
 */
export function ProtectedRoute({ children, fallback }: ProtectedRouteProps) {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  // En modo demo se omite por completo el flujo de autenticacion.
  if (SKIP_AUTH) {
    return <>{children}</>;
  }

  if (loading) {
    return <>{fallback ?? <div role="status">Cargando&hellip;</div>}</>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <>{children}</>;
}

export default ProtectedRoute;
