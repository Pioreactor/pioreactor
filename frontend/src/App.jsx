import React from "react";
import { BrowserRouter as Router, Routes, Route, useLocation } from "react-router";
import { ThemeProvider, createTheme} from '@mui/material/styles';
import CssBaseline from "@mui/material/CssBaseline";
import { StyledEngineProvider } from '@mui/material/styles';


import TactileButtonNotification from "./components/TactileButtonNotification";
import ErrorSnackbar from "./components/ErrorSnackbar";
import SideNavAndHeader from "./components/SideNavAndHeader";
import MissingWorkerModelModal from "./components/MissingWorkerModelModal";
import ErrorBoundary from "./components/ErrorBoundary";
import { ConfirmProvider } from 'material-ui-confirm';
import {getConfig} from "./utilities"
import { MQTTProvider } from './providers/MQTTContext';
import { ExperimentProvider } from './providers/ExperimentContext';


import "@fontsource/roboto/400.css"
import "@fontsource/roboto/500.css"
import "@fontsource/roboto/700.css"

const ExperimentOverview = React.lazy(() => import("./ExperimentOverview"));
const ExportData = React.lazy(() => import("./ExportData"));
const Pioreactors = React.lazy(() => import("./Pioreactors"));
const Pioreactor = React.lazy(() => import("./Pioreactor"));
const StartNewExperiment = React.lazy(() => import("./StartNewExperiment"));
const SingleCalibrationPage = React.lazy(() => import("./SingleCalibrationPage"));
const SingleEstimatorPage = React.lazy(() => import("./SingleEstimatorPage"));
const CreateExperimentProfile = React.lazy(() => import("./CreateExperimentProfile"));
const EditExperimentProfile = React.lazy(() => import("./EditExperimentProfile"));
const EditConfig = React.lazy(() => import("./EditConfig"));
const Updates = React.lazy(() => import("./Updates"));
const Plugins = React.lazy(() => import("./Plugins"));
const Profiles = React.lazy(() =>
  import("./Profiles").then((module) => ({ default: module.Profiles }))
);
const Inventory = React.lazy(() => import("./Inventory"));
const Leader = React.lazy(() => import("./Leader"));
const Logs = React.lazy(() => import("./Logs"));
const SystemLogs = React.lazy(() => import("./SystemLogs"));
const Experiments = React.lazy(() => import("./Experiments"));
const Calibrations = React.lazy(() => import("./Calibrations"));
const CalibrationCoverage = React.lazy(() => import("./CalibrationCoverage"));
const Estimators = React.lazy(() => import("./Estimators"));
const Protocols = React.lazy(() => import("./Protocols"));


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
      main: '#DF1A0C',
    },
  },
  components: {
  },
});


const NotFound = () => {
  return (
    <>
      <h1>Page Not Found</h1>
      <p>Sorry, the page you are looking for could not be found.</p>
    </>
  );
};

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
          <Router
            future={{
              v7_relativeSplatPath: true,
              v7_startTransition: true,
            }}
          >
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
  const [config, setConfig] = React.useState({})

  React.useEffect(() => {
    getConfig(setConfig)
  }, [])

  return (
    <div style={{display: 'flex'}}>
      <ErrorBoundary>
        <ExperimentProvider>
          <SideNavAndHeader />
          <main style={{flexGrow: 1, paddingTop: theme.spacing(9), paddingLeft: theme.spacing(4), paddingRight: theme.spacing(4)}}>
            <div className="pageContainer">
              <MQTTProvider name="global" config={config}>
                <React.Suspense fallback={<div style={{ padding: theme.spacing(2) }}>Loading...</div>}>
                  <Routes>
                    <Route path="/export-data" element={<ExportData title="Pioreactor ~ Export data"/>}/>
                    <Route path="/start-new-experiment" element={<StartNewExperiment title="Pioreactor ~ Start new experiment" />}/>
                    <Route path="/overview" element={<ExperimentOverview title="Pioreactor ~ Overview"/>}/>
                    <Route path="/plugins" element={<Plugins title="Pioreactor ~ Plugins"/>}/>
                    <Route path="/plugins/:pioreactorUnit/" element={<Plugins title="Pioreactor ~ Plugins"/>}/>
                    <Route path="/experiments" element={<Experiments title="Pioreactor ~ Past experiments"/>}/>
                    <Route path="/experiment-profiles" element={<Profiles title="Pioreactor ~ Experiment profiles"/>}/>
                    <Route path="/experiment-profiles/:profileFilename/" element={<Profiles title="Pioreactor ~ Experiment profiles"/>}/>
                    <Route path="/experiment-profiles/new" element={<CreateExperimentProfile title="Pioreactor ~ Create experiment profile"/>}/>
                    <Route path="/experiment-profiles/:profileFilename/edit" element={<EditExperimentProfile title="Pioreactor ~ Edit experiment profile"/>}/>
                    <Route path="/config" element={<EditConfig title="Pioreactor ~ Configuration"/>}/>
                    <Route path="/config/:pioreactorUnit/" element={<EditConfig title="Pioreactor ~ Configuration"/>}/>
                    <Route path="/leader" element={<Leader title="Pioreactor ~ Leader"/>}/>
                    <Route path="/calibrations" element={<Calibrations title="Pioreactor ~ Calibrations"/>}/>
                    <Route path="/calibration-coverage" element={<CalibrationCoverage title="Pioreactor ~ Calibration Coverage"/>}/>
                    <Route path="/calibrations/:pioreactorUnit/" element={<Calibrations title="Pioreactor ~ Calibrations"/>}/>
                    <Route path="/calibrations/:pioreactorUnit/:device" element={<Calibrations title="Pioreactor ~ Calibrations"/>}/>
                    <Route path="/calibrations/:pioreactorUnit/:device/:calibrationName" element={<SingleCalibrationPage title="Pioreactor ~ Calibration"/>}/>
                    <Route path="/estimators" element={<Estimators title="Pioreactor ~ Estimators"/>}/>
                    <Route path="/estimators/:pioreactorUnit/" element={<Estimators title="Pioreactor ~ Estimators"/>}/>
                    <Route path="/estimators/:pioreactorUnit/:device" element={<Estimators title="Pioreactor ~ Estimators"/>}/>
                    <Route path="/estimators/:pioreactorUnit/:device/:estimatorName" element={<SingleEstimatorPage title="Pioreactor ~ Estimator"/>}/>
                    <Route path="/protocols" element={<Protocols title="Pioreactor ~ Protocols"/>}/>
                    <Route path="/protocols/:pioreactorUnit" element={<Protocols title="Pioreactor ~ Protocols"/>}/>
                    <Route path="/protocols/:pioreactorUnit/:device" element={<Protocols title="Pioreactor ~ Protocols"/>}/>
                    <Route path="/pioreactors" element={ <Pioreactors title="Pioreactor ~ Pioreactors"/>}/>
                    <Route path="/pioreactors/:pioreactorUnit" element={ <Pioreactor title="Pioreactor ~ Pioreactor"/>}/>
                    <Route path="/updates" element={<Updates title="Pioreactor ~ Updates"/>}/>
                    <Route path="/inventory" element={<Inventory title="Pioreactor ~ Inventory"/>}/>
                    <Route path="/logs" element={<Logs title="Pioreactor ~ Logs"/>}/>
                    <Route path="/logs/:pioreactorUnit" element={<Logs title="Pioreactor ~ Logs"/>}/>
                    <Route path="/system-logs" element={<SystemLogs title="Pioreactor ~ System Logs"/>}/>
                    <Route path="/system-logs/:pioreactorUnit" element={<SystemLogs title="Pioreactor ~ System Logs"/>}/>
                    <Route path="/" element={<ExperimentOverview title="Pioreactor ~ Overview"/>}/>
                    <Route path="*" element={<NotFound />} />
                  </Routes>
                </React.Suspense>
                <MissingWorkerModelModal />
                <ErrorSnackbar />
                <TactileButtonNotification />
              </MQTTProvider>
            </div>
          </main>
        </ExperimentProvider>
      </ErrorBoundary>
    </div>
)}

export default App;
