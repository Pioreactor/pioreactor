import React from "react";
import { BrowserRouter as Router, Routes, Route, useLocation } from "react-router-dom";
import { ThemeProvider, createTheme} from '@mui/material/styles';
import CssBaseline from "@mui/material/CssBaseline";
import { StyledEngineProvider } from '@mui/material/styles';


import TactileButtonNotification from "./components/TactileButtonNotification";
import ErrorSnackbar from "./components/ErrorSnackbar";
import ExperimentOverview from "./ExperimentOverview";
import ExportData from "./ExportData";
import Pioreactors from "./Pioreactors";
import StartNewExperiment from "./StartNewExperiment";
import CreateExperimentProfile from "./CreateExperimentProfile";
import EditExperimentProfile from "./EditExperimentProfile";
import EditConfig from "./EditConfig";
import Updates from "./Updates";
import Plugins from "./Plugins";
import Profiles from "./Profiles";
//import Analysis from "./Analysis";
import Experiments from "./Experiments";
import SideNavAndHeader from "./components/SideNavAndHeader";
import ErrorBoundary from "./components/ErrorBoundary";
import { ConfirmProvider } from 'material-ui-confirm';
import { ProSidebarProvider } from "react-pro-sidebar";
import {getConfig} from "./utilities"
import { MQTTProvider } from './MQTTContext';


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
            <ProSidebarProvider>
            <ScrollToTop/>
            <ConfirmProvider>
              <CssBaseline />
              <MainSite />
            </ConfirmProvider>
            </ProSidebarProvider>
          </Router>
        </ThemeProvider>
      </StyledEngineProvider>
    </React.StrictMode>
  );
}

function MainSite() {
  const [config, setConfig] = React.useState({})

  React.useEffect(() => {
    getConfig(setConfig)
  }, [])

  return (
    <div style={{display: 'flex'}}>
      <ErrorBoundary>
        <SideNavAndHeader />
        <main style={{flexGrow: 1, paddingTop: theme.spacing(9), paddingLeft: theme.spacing(4), paddingRight: theme.spacing(4)}}>
          <div className="pageContainer">
            <MQTTProvider name="global" config={config}>
              <Routes>
                <Route path="/export-data" element={<ExportData title="Pioreactor ~ Export data"/>}/>
                <Route path="/start-new-experiment" element={<StartNewExperiment title="Pioreactor ~ Start new experiment" />}/>
                <Route path="/overview" element={<ExperimentOverview title="Pioreactor ~ Overview"/>}/>
                <Route path="/plugins" element={<Plugins title="Pioreactor ~ Plugins"/>}/>
                <Route path="/experiments" element={<Experiments title="Pioreactor ~ Past experiments"/>}/>
                <Route path="/experiment-profiles" element={<Profiles title="Pioreactor ~ Experiment profiles"/>}/>
                <Route path="/create-experiment-profile" element={<CreateExperimentProfile title="Pioreactor ~ Create experiment profile"/>}/>
                <Route path="/edit-experiment-profile" element={<EditExperimentProfile title="Pioreactor ~ Edit experiment profile"/>}/>
                <Route path="/config" element={<EditConfig title="Pioreactor ~ Configuration"/>}/>
                <Route path="/pioreactors" element={ <Pioreactors title="Pioreactor ~ Pioreactors"/>}/>
                <Route path="/updates" element={<Updates title="Pioreactor ~ Updates"/>}/>
                <Route path="/" element={<ExperimentOverview title="Pioreactor ~ Overview"/>}/>
              </Routes>
              <ErrorSnackbar config={config} />
              <TactileButtonNotification config={config}  />
            </MQTTProvider>
          </div>
        </main>
      </ErrorBoundary>
    </div>
)}

export default App;
