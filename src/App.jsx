import React from "react";
import { BrowserRouter as Router, Switch, Route, useLocation } from "react-router-dom";
import { ThemeProvider, createTheme} from '@mui/material/styles';
import CssBaseline from "@mui/material/CssBaseline";
import { StyledEngineProvider } from '@mui/material/styles';


import TactileButtonNotification from "./components/TactileButtonNotification";
import ErrorSnackbar from "./components/ErrorSnackbar";
import ExperimentOverview from "./ExperimentOverview";
import ExportData from "./ExportData";
import Pioreactors from "./Pioreactors";
import StartNewExperiment from "./StartNewExperiment";
import Calibrations from "./Calibrations";
import EditConfig from "./EditConfig";
import Updates from "./Updates";
import Plugins from "./Plugins";
import Analysis from "./Analysis";
import Feedback from "./Feedback";
import SideNavAndHeader from "./components/SideNavAndHeader";
import ErrorBoundary from "./components/ErrorBoundary";
import { ConfirmProvider } from 'material-ui-confirm';

import "@fontsource/roboto/300.css"
import "@fontsource/roboto/400.css"
import "@fontsource/roboto/500.css"
import "@fontsource/roboto/700.css"
import './styles.css';

const theme = createTheme({
  palette: {
    background: {
      default: "#f6f6f7",
    },
    primary: {
      // light: will be calculated from palette.primary.main,
      main: '#5331CA',
      // dark: will be calculated from palette.primary.main,
      // contrastText: will be calculated to contrast with palette.primary.main
    },
    secondary: {
      main: '#f44336',
    },
  },
});


function ScrollToTop() {
  const { pathname } = useLocation();

  React.useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return null;
}


function App() {
  return (
    <React.StrictMode>
      <StyledEngineProvider injectFirst>
        <ThemeProvider theme={theme}>
          <Router>
            <ScrollToTop/>
            <ConfirmProvider>
              <CssBaseline />
              <MainSite />
            </ConfirmProvider>
          </Router>
        </ThemeProvider>
      </StyledEngineProvider>
    </React.StrictMode>
  );
}

function MainSite() {
  return (
    <div style={{display: 'flex'}}>
      <ErrorBoundary>
        <SideNavAndHeader />
        <main style={{flexGrow: 1, paddingTop: theme.spacing(9), paddingLeft: theme.spacing(4), paddingRight: theme.spacing(4)}}>
          <div className="pageContainer">
            <Switch>
              <Route path="/export-data">
                <ExportData title="Pioreactor ~ Export data"/>
              </Route>
              <Route path="/start-new-experiment">
                <StartNewExperiment title="Pioreactor ~ Start new experiment" />
              </Route>
              <Route path="/overview">
                <ExperimentOverview title="Pioreactor ~ Overview"/>
              </Route>
              <Route path="/plugins">
                <Plugins title="Pioreactor ~ Plugins"/>
              </Route>
              <Route path="/analysis">
                <Analysis title="Pioreactor ~ Analysis"/>
              </Route>
              <Route path="/config">
                <EditConfig title="Pioreactor ~ Configuration"/>
              </Route>
              <Route path="/pioreactors" exact>
                <Pioreactors title="Pioreactor ~ Pioreactors"/>
              </Route>
              <Route path="/updates">
                <Updates title="Pioreactor ~ Updates"/>
              </Route>
              <Route path="/feedback">
                <Feedback title="Pioreactor ~ Feedback"/>
              </Route>
              <Route path="/calibrations">
                <Calibrations title="Pioreactor ~ Calibrations"/>
              </Route>
              <Route path="/">
                <ExperimentOverview title="Pioreactor ~ Pioreactor"/>
              </Route>
            </Switch>
            <ErrorSnackbar />
            <TactileButtonNotification />
          </div>
        </main>
      </ErrorBoundary>
    </div>
)}

export default App;
