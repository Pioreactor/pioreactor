import React from "react";
import { BrowserRouter as Router, Switch, Route } from "react-router-dom";
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
import {parseINIString} from "./utilities"


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



function App() {
  return (
    <React.StrictMode>
      <StyledEngineProvider injectFirst>
        <ThemeProvider theme={theme}>
          <ConfirmProvider>
            <CssBaseline />
            <MainSite />
          </ConfirmProvider>
        </ThemeProvider>
      </StyledEngineProvider>
    </React.StrictMode>
  );
}

function MainSite() {
  const [config, setConfig] = React.useState({})

  React.useEffect(() => {

    function getConfig() {
      fetch("/api/get_config/config.ini")
        .then((response) => {
            if (response.ok) {
              return response.text();
            } else {
              throw new Error('Something went wrong');
            }
          })
        .then((config) => {
          setConfig(parseINIString(config)); // TODO: parse on server side and send a json object
        })
        .catch((error) => {})
    }
    getConfig();
  }, [])
  return (
    <div style={{display: 'flex'}}>
      <ErrorBoundary config={config}>
        <SideNavAndHeader />
        <main style={{flexGrow: 1, paddingTop: theme.spacing(9), paddingLeft: theme.spacing(4), paddingRight: theme.spacing(4)}}>
          <Router>
            <div className="pageContainer">
              <Switch>
                <Route path="/export-data">
                  <ExportData config={config} title="Pioreactor ~ Export data"/>
                </Route>
                <Route path="/start-new-experiment">
                  <StartNewExperiment config={config} title="Pioreactor ~ Start new experiment" />
                </Route>
                <Route path="/overview">
                  <ExperimentOverview config={config} title="Pioreactor ~ Overview"/>
                </Route>
                <Route path="/plugins">
                  <Plugins config={config} title="Pioreactor ~ Plugins"/>
                </Route>
                <Route path="/analysis">
                  <Analysis config={config} title="Pioreactor ~ Analysis"/>
                </Route>
                <Route path="/config">
                  <EditConfig config={config} title="Pioreactor ~ Configuration"/>
                </Route>
                <Route path="/pioreactors" exact>
                  <Pioreactors config={config} title="Pioreactor ~ Pioreactors"/>
                </Route>
                <Route path="/updates">
                  <Updates config={config} title="Pioreactor ~ Updates"/>
                </Route>
                <Route path="/feedback">
                  <Feedback config={config} title="Pioreactor ~ Feedback"/>
                </Route>
                <Route path="/calibrations">
                  <Calibrations config={config} title="Pioreactor ~ Calibrations"/>
                </Route>
                <Route path="/">
                  <ExperimentOverview config={config} title="Pioreactor ~ Pioreactor"/>
                </Route>
              </Switch>
              <ErrorSnackbar config={config} />
              <TactileButtonNotification config={config}/>
            </div>
          </Router>
        </main>
      </ErrorBoundary>
    </div>
)}

export default App;
