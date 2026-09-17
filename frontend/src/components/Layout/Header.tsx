// components/Layout/Header.tsx
//
// Encabezado con identidad Any2cloud: logotipo (nube + wordmark) en version
// inversa sobre el degradado de marca. En modo demo muestra un usuario simulado.

import { useAuth } from '../../hooks/useAuth';
import { SKIP_AUTH, DEMO_USER } from '../../config/demo';

function getUserDisplayName(user: {
  username: string;
  signInDetails?: { loginId?: string };
} | null): string | null {
  if (!user) return null;
  return user.signInDetails?.loginId ?? user.username ?? null;
}

export function Header() {
  const { user, isAuthenticated, logout } = useAuth();

  const effectiveUser = SKIP_AUTH ? DEMO_USER : user;
  const effectiveAuth = SKIP_AUTH ? true : isAuthenticated;
  const displayName = getUserDisplayName(effectiveUser);

  const handleLogout = () => {
    if (SKIP_AUTH) return;
    void logout();
  };

  return (
    <header className="app-header">
      <div className="app-header__brand">
        <h1 className="app-header__title">
          ANY<span className="app-header__title-2">2</span>CLOUD
        </h1>
        <span className="app-header__product">Purdy Renting</span>
      </div>

      {effectiveAuth && (
        <div className="app-header__user">
          {displayName && (
            <span className="app-header__user-name" title={displayName}>
              {displayName}
            </span>
          )}
          <button
            type="button"
            className="app-header__logout"
            onClick={handleLogout}
            disabled={SKIP_AUTH}
          >
            Cerrar sesion
          </button>
        </div>
      )}
    </header>
  );
}

export default Header;
