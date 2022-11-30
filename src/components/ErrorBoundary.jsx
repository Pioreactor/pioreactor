import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.log(error);
  }

  render() {
    if (this.state.hasError) {
      return (
      <React.Fragment>
        <div style={{maxWidth: 700, margin: "auto"}}>
          <div>
            <h1>Something went wrong with the PioreactorUI!</h1>
            <h3>Don't worry. It's our fault. Here's what you can do:</h3>
            <p> Looks like there's a bug in the UI. See the console (⌘+⌥+i) for error information. We would appreciate it
            if you create an issue in <a href="https://github.com/Pioreactor/pioreactorui/issues">Github</a> for us, with the information in the console (⌘+⌥+i).</p>
          </div>
        </div>
      </React.Fragment>
      )
    }

    return this.props.children; 
  }
}

export default ErrorBoundary;
