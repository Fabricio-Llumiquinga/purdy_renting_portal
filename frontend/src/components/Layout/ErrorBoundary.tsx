// components/Layout/ErrorBoundary.tsx
//
// React error boundary for the Purdy Renting platform. It catches rendering
// errors in its subtree and shows a graceful fallback UI instead of a blank
// screen. All user-facing text is in Spanish per Requirement 9.1/9.2 (Spanish
// Language Interface / error messages in Spanish).
//
// Error boundaries must be class components: only components implementing
// `getDerivedStateFromError` / `componentDidCatch` can catch render-phase
// errors from their descendants.

import { Component, type ErrorInfo, type ReactNode } from 'react';

export interface ErrorBoundaryProps {
  /** The subtree that this boundary protects. */
  children: ReactNode;
  /**
   * Optional custom fallback UI. When omitted, a default Spanish error message
   * with a "reload" action is rendered.
   */
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  /** True once an error has been caught in the subtree. */
  hasError: boolean;
  /** The caught error, retained for optional display/logging. */
  error: Error | null;
}

/**
 * Catches errors thrown while rendering descendant components and renders a
 * Spanish fallback message instead of crashing the whole app.
 */
export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  /** Update state so the next render shows the fallback UI. */
  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  /** Log error details for diagnostics. */
  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary capturó un error:', error, errorInfo);
  }

  private handleReload = () => {
    // Reset the boundary; a full reload clears any corrupt in-memory state.
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div role="alert" className="error-boundary">
          <h2 className="error-boundary__title">Ocurrió un error inesperado.</h2>
          <p className="error-boundary__message">
            Lo sentimos, algo salió mal. Por favor, vuelva a intentarlo.
          </p>
          <button
            type="button"
            className="error-boundary__retry"
            onClick={this.handleReload}
          >
            Recargar la página
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
