import { Component } from "react";

const AUTO_RELOAD_MS = 60000;

// A kiosk has no address bar or dev tools, so a render error must never leave a
// blank screen: offer a reload, and reload by itself if nobody is around.
export default class DisplayErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error(error, info.componentStack);
    this.timer = setTimeout(() => window.location.reload(), AUTO_RELOAD_MS);
  }

  componentWillUnmount() {
    clearTimeout(this.timer);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="empty" role="alert">
        <h1 style={{ fontSize: "1.2rem", marginBottom: "0.5rem" }}>Something went wrong with the display.</h1>
        <p className="muted">{String(this.state.error.message || this.state.error)}</p>
        <p className="muted">It will reload automatically in a minute.</p>
        <div className="btn-row" style={{ justifyContent: "center", marginTop: "1rem" }}>
          <button
            className="btn"
            onClick={() => {
              window.location.hash = "/overview";
              window.location.reload();
            }}
          >
            Back to Pioreactors
          </button>
          <button className="btn primary" onClick={() => window.location.reload()}>
            Reload display
          </button>
        </div>
      </div>
    );
  }
}
