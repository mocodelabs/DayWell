import { Component, type ErrorInfo, type ReactNode } from "react";

/** Last-resort guard: a rendering bug shows a calm, recoverable message instead of a blank screen. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("DayWell UI error", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="grid min-h-dvh place-items-center p-6 text-center">
        <div className="max-w-sm">
          <p className="text-lg font-semibold">Something went wrong on this screen.</p>
          <p className="mt-2 text-sm text-muted">Your data is safe — nothing was lost. Reloading usually fixes it.</p>
          <button className="mt-4 rounded-lg bg-primary px-4 py-2 font-medium text-on-primary" onClick={() => window.location.reload()}>Reload DayWell</button>
        </div>
      </div>
    );
  }
}
