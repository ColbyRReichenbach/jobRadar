import * as React from 'react';
import { type ErrorInfo, type ReactNode } from 'react';
import { Logo } from './Logo';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  errorMessage: string | null;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  declare props: Readonly<ErrorBoundaryProps>;

  state: ErrorBoundaryState = {
    hasError: false,
    errorMessage: null,
  };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      errorMessage: error.message || 'Unexpected dashboard error',
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Dashboard render failed', error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F5F5F0] p-4">
        <div className="w-full max-w-lg">
          <div className="text-center mb-8">
            <Logo className="mx-auto mb-4 h-20 w-20" />
            <h1 className="text-3xl tracking-tight font-serif font-bold text-slate-900">
              Opportunity Radar hit an unexpected error
            </h1>
            <p className="mt-2 text-slate-500 font-serif italic">
              The dashboard could not finish rendering. Reload to try again.
            </p>
          </div>

          <div className="bg-white rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-slate-100 p-8">
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              {this.state.errorMessage || 'Unexpected dashboard error'}
            </div>

            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              <button
                onClick={this.handleReload}
                className="flex-1 py-3.5 bg-slate-800 text-white rounded-xl font-medium hover:bg-slate-900 transition-colors shadow-sm"
              >
                Reload Dashboard
              </button>
              <a
                href="/"
                className="flex-1 py-3.5 px-4 bg-white border border-slate-200 rounded-xl font-medium text-slate-700 hover:bg-slate-50 transition-colors shadow-sm text-center"
              >
                Return Home
              </a>
            </div>
          </div>
        </div>
      </div>
    );
  }
}
