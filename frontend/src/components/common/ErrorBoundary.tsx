import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props { children: ReactNode }
interface State { error: Error | null }
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };
  static getDerivedStateFromError(error: Error): State { return { error }; }
  componentDidCatch(error: Error, info: ErrorInfo): void { console.error("BookBuddy route failed", error, info); }
  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return <main className="centered-state" role="alert"><p className="eyebrow">BookBuddy recovered safely</p><h1>This screen could not be opened.</h1><p>{this.state.error.message}</p><button className="primary" onClick={() => window.location.assign("/")}>Return to library</button></main>;
  }
}
