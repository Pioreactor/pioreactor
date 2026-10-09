import { useCallback, useEffect, useMemo, useState } from "react";
import { ExperimentProvider, useExperiment } from "../providers/ExperimentContext";
import { MQTTProvider } from "../providers/MQTTContext";
import { RunningProfilesProvider } from "../providers/RunningProfilesContext";
import { getConfig, getRelabelMap } from "../utils/config";
import { experimentPathSegment } from "../utils/url";
import { ColorCycler, colors } from "../utils/color";
import { KeyboardProvider } from "./Keyboard";
import { ConfirmProvider, Icon, ToastProvider } from "./ui";
import { useMqttConnected, useNow } from "./hooks";
import { DisplayContext, navigate } from "./context";
import Overview from "./screens/Overview";
import Unit from "./screens/Unit";
import Charts from "./screens/Charts";
import Experiment from "./screens/Experiment";
import Logs from "./screens/Logs";
import System from "./screens/System";


const NAV = [
  { screen: "overview", label: "Pioreactors", icon: "units" },
  { screen: "charts", label: "Charts", icon: "chart" },
  { screen: "experiment", label: "Experiment", icon: "experiments" },
  { screen: "logs", label: "Logs", icon: "logs" },
  { screen: "system", label: "System", icon: "system" },
];

function parseHash(hash) {
  const [screen = "overview", ...rest] = hash.replace(/^#\/?/, "").split("/");
  return {
    screen: screen || "overview",
    param: rest.length ? decodeURIComponent(rest.join("/")) : null,
  };
}

function useHashRoute() {
  const [route, setRoute] = useState(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

function StatusClock() {
  const now = useNow(15000);
  const connected = useMqttConnected();
  const time = new Date(now).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return (
    <div className="rail-status" aria-label={connected ? "Live data connected" : "Live data disconnected"}>
      <span className={`dot ${connected ? "ok" : "bad"}`} />
      <span className="num">{time}</span>
    </div>
  );
}

// The provider never retries a failed first connection, so a kiosk that booted
// before the broker was ready would stay offline. Reload once in that case.
function ReconnectGuard() {
  const connected = useMqttConnected();
  const [everConnected, setEverConnected] = useState(false);
  useEffect(() => {
    if (connected) setEverConnected(true);
  }, [connected]);
  useEffect(() => {
    if (connected || everConnected) return undefined;
    const timer = setTimeout(() => window.location.reload(), 60000);
    return () => clearTimeout(timer);
  }, [connected, everConnected]);
  return null;
}

function Shell() {
  const { screen, param } = useHashRoute();
  const active = screen === "unit" ? "overview" : screen;

  let page;
  switch (screen) {
    case "unit":
      page = <Unit unit={param} key={param} />;
      break;
    case "charts":
      page = <Charts />;
      break;
    case "experiment":
      page = <Experiment tab={param} key={param || "experiment"} />;
      break;
    case "logs":
      page = <Logs />;
      break;
    case "system":
      page = <System />;
      break;
    default:
      page = <Overview />;
  }

  return (
    <div className="app">
      <nav className="rail">
        {NAV.map((item) => (
          <button
            key={item.screen}
            className={`rail-item ${active === item.screen ? "active" : ""}`}
            aria-current={active === item.screen ? "page" : undefined}
            onClick={() => navigate(item.screen)}
          >
            <Icon name={item.icon} />
            {item.label}
          </button>
        ))}
        <StatusClock />
      </nav>
      <main className="main">{page}</main>
      <ReconnectGuard />
    </div>
  );
}

function ClusterState({ config, children }) {
  const { experimentMetadata } = useExperiment();
  const experiment = experimentMetadata?.experiment;
  const [units, setUnits] = useState(null);
  const [labels, setLabels] = useState({});
  const unitColors = useMemo(() => new ColorCycler(colors), []);
  const unitColor = useCallback((unit) => unitColors[unit], [unitColors]);
  const labelFor = useCallback((unit) => labels[unit] || unit, [labels]);

  const reloadUnits = useCallback(async () => {
    if (!experiment) return;
    try {
      const response = await fetch(`/api/experiments/${experimentPathSegment(experiment)}/workers`);
      if (response.ok) setUnits(await response.json());
    } catch (error) {
      console.error("Failed to load workers", error);
    }
  }, [experiment]);

  useEffect(() => {
    setUnits(null);
    if (!experiment) return undefined;
    reloadUnits();
    getRelabelMap((map) => setLabels(map || {}), experiment);
    const timer = setInterval(reloadUnits, 60000);
    return () => clearInterval(timer);
  }, [experiment, reloadUnits]);

  const value = useMemo(
    () => ({
      config,
      experiment,
      experimentMetadata,
      units,
      labels,
      setLabels,
      reloadUnits,
      leader: config["cluster.topology"]?.leader_hostname,
      unitColor,
      labelFor,
    }),
    [config, experiment, experimentMetadata, units, labels, reloadUnits, unitColor, labelFor],
  );

  return (
    <RunningProfilesProvider experiment={experiment} leaderHostname={value.leader}>
      <DisplayContext.Provider value={value}>{children}</DisplayContext.Provider>
    </RunningProfilesProvider>
  );
}

export default function DisplayApp() {
  const [config, setConfig] = useState(null);

  useEffect(() => {
    let cancelled = false;
    let loaded = false;
    let timer;
    // The display can start before the web server is fully ready; keep trying.
    const load = () =>
      getConfig((parsed) => {
        loaded = true;
        if (!cancelled) setConfig(parsed);
      }).then(() => {
        if (!loaded && !cancelled) timer = setTimeout(load, 3000);
      });
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  if (!config) {
    return <div className="empty">Connecting to the Pioreactor...</div>;
  }

  return (
    <ToastProvider>
      <ConfirmProvider>
        <KeyboardProvider>
          <ExperimentProvider>
            <MQTTProvider name="display" config={config}>
              <ClusterState config={config}>
                <Shell />
              </ClusterState>
            </MQTTProvider>
          </ExperimentProvider>
        </KeyboardProvider>
      </ConfirmProvider>
    </ToastProvider>
  );
}
