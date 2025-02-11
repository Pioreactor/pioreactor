import React from 'react';


class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, errorMsg: "" };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error(error);
    console.log(errorInfo.componentStack);
    this.setState({errorMsg: `${error.message}


      ${errorInfo.componentStack}

      `} )
  }

  render() {
    if (this.state.hasError) {
      return (
      <React.Fragment>
        <div style={{maxWidth: 700, margin: "auto"}}>
          <div>
            <h1>Something went wrong with the PioreactorUI!</h1>
            <h3>Don't worry. It's our fault. Here's what you can do:</h3>
            <p> Looks like there's a bug in the UI. See the below for error information. We would appreciate it
            if you create an issue in <a href="https://github.com/Pioreactor/pioreactorui/issues">Github</a> for us, with the information below.</p>
          </div>
          <div>
            <code>
            URL: {window.location.href}
            </code>
            <br/>
            <code>
            {this.state.errorMsg}
            </code>
          </div>
        </div>
      </React.Fragment>
      )
    }

    return this.props.children; 
  }
}

export default ErrorBoundary;
