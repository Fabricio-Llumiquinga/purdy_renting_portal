// App.tsx
//
// Root application component. Wires up routing (react-router-dom v6) and guards
// the main views behind authentication (omitida en modo demo).

import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom';
import { ProtectedRoute } from './components/Auth/ProtectedRoute';
import { LoginPage } from './components/Auth/LoginPage';
import { Header } from './components/Layout/Header';
import { ErrorBoundary } from './components/Layout/ErrorBoundary';
import { RequestForm } from './components/Request/RequestForm';
import { RequestTable } from './components/Tracking/RequestTable';
import { IS_DEMO_MODE } from './config/demo';

function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <Header />
      {IS_DEMO_MODE && (
        <div className="demo-banner" role="note">
          Modo demo (vista previa local, sin backend). Los datos son de ejemplo.
        </div>
      )}
      <nav className="app-nav" aria-label="Navegacion principal">
        <NavLink to="/" end>Crear solicitud</NavLink>
        <NavLink to="/tracking">Seguimiento</NavLink>
      </nav>
      <main className="app-content">{children}</main>
    </div>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          <Route
            path="/"
            element={
              <ProtectedRoute>
                <AppLayout>
                  <RequestForm />
                </AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/tracking"
            element={
              <ProtectedRoute>
                <AppLayout>
                  <RequestTable />
                </AppLayout>
              </ProtectedRoute>
            }
          />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

export default App;