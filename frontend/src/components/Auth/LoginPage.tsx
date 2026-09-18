// components/Auth/LoginPage.tsx
//
// Pagina de inicio de sesion con formulario propio (email + password) sobre
// Cognito nativo. Maneja el reto NEW_PASSWORD_REQUIRED para usuarios recien
// creados por el administrador (que deben fijar su contrasena en el primer
// acceso). Tras un login exitoso, redirige a la ruta de origen (o a "/").

import { useState, type FormEvent } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

interface LocationState {
  from?: { pathname?: string };
}

export function LoginPage() {
  const { signIn, completeNewPassword } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [needsNewPassword, setNeedsNewPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const redirectTarget =
    (location.state as LocationState | null)?.from?.pathname ?? '/';

  const goToApp = () => navigate(redirectTarget, { replace: true });

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await signIn(email.trim(), password);
      if (result.isSignedIn) {
        goToApp();
      } else if (result.requiresNewPassword) {
        setNeedsNewPassword(true);
      } else {
        setError('No se pudo iniciar sesion. Verifique sus credenciales.');
      }
    } catch (err) {
      setError(mapAuthError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleNewPassword = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError('Las contrasenas no coinciden.');
      return;
    }
    setSubmitting(true);
    try {
      const result = await completeNewPassword(newPassword);
      if (result.isSignedIn) {
        goToApp();
      } else {
        setError('No se pudo establecer la nueva contrasena.');
      }
    } catch (err) {
      setError(mapAuthError(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <h1 className="app-header__title">
            ANY<span className="app-header__title-2">2</span>CLOUD
          </h1>
          <span className="app-header__product">Purdy Renting</span>
        </div>

        {!needsNewPassword ? (
          <form onSubmit={handleLogin} className="login-form" aria-label="Iniciar sesion">
            <h2>Iniciar sesion</h2>
            <label htmlFor="email">Correo electronico</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <label htmlFor="password">Contrasena</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            {error && <p role="alert" className="login-error">{error}</p>}
            <button type="submit" disabled={submitting}>
              {submitting ? 'Ingresando...' : 'Ingresar'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleNewPassword} className="login-form" aria-label="Nueva contrasena">
            <h2>Establecer nueva contrasena</h2>
            <p className="login-hint">
              Es su primer acceso. Defina una contrasena nueva para continuar.
            </p>
            <label htmlFor="newPassword">Nueva contrasena</label>
            <input
              id="newPassword"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
            />
            <label htmlFor="confirmPassword">Confirmar contrasena</label>
            <input
              id="confirmPassword"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
            />
            {error && <p role="alert" className="login-error">{error}</p>}
            <button type="submit" disabled={submitting}>
              {submitting ? 'Guardando...' : 'Guardar y continuar'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

/** Traduce errores comunes de Cognito/Amplify a mensajes en espanol. */
function mapAuthError(err: unknown): string {
  const name = (err as { name?: string })?.name ?? '';
  switch (name) {
    case 'NotAuthorizedException':
      return 'Correo o contrasena incorrectos.';
    case 'UserNotFoundException':
      return 'El usuario no existe.';
    case 'PasswordResetRequiredException':
      return 'Debe restablecer su contrasena. Contacte al administrador.';
    case 'InvalidPasswordException':
      return 'La contrasena no cumple los requisitos de seguridad.';
    case 'TooManyRequestsException':
    case 'LimitExceededException':
      return 'Demasiados intentos. Intente de nuevo en unos minutos.';
    default:
      return 'Ocurrio un error al iniciar sesion. Intente de nuevo.';
  }
}

export default LoginPage;
