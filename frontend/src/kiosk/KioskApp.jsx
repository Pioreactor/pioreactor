import { useState } from "react";
import { useKiosk } from "./context";
import { Icon } from "./icons";
import { navigate, usePage } from "./router";
import ExperimentSheet from "./ExperimentSheet";
import Activities from "./pages/Activities";
import Calibrations from "./pages/Calibrations";
import Charts from "./pages/Charts";
import Cluster from "./pages/Cluster";
import Logs from "./pages/Logs";
import System from "./pages/System";
import Usb from "./pages/Usb";
import { hasDrive } from "./usb";

// Control (the Activities page) also owns /k/dosing and /k/leds, its other tabs;
// Cluster owns /k/experiments. Cluster is on leaders' screens only (standalone
// included): a worker's screen controls only its own unit.
const PAGES = [
  { page: "", label: "Control", icon: "control", Component: Activities, also: ["dosing", "leds"] },
  { page: "charts", label: "Charts", icon: "chart", Component: Charts },
  { page: "calibrations", label: "Calibrations", icon: "calibration", Component: Calibrations },
  { page: "logs", label: "Logs", icon: "logs", Component: Logs },
  { page: "cluster", label: "Cluster", icon: "cluster", Component: Cluster, also: ["experiments"], leaderOnly: true },
  // Enabled while a drive is plugged in.
  { page: "usb", label: "USB", icon: "usb", Component: Usb, needsDrive: true },
  { page: "system", label: "System", icon: "system", Component: System },
];

function Rail({ pages, active }) {
  const { usb } = useKiosk();
  const drive = hasDrive(usb);
  return (
    <nav className="rail" aria-label="Pages">
      {pages.map((item) => (
        <button
          type="button"
          key={item.page}
          className={`rail-item ${active === item.page ? "active" : ""}`}
          aria-current={active === item.page ? "page" : undefined}
          disabled={item.needsDrive && !drive && active !== item.page}
          onClick={() => navigate(item.page)}
        >
          <Icon name={item.icon} />
          {item.label}
        </button>
      ))}
    </nav>
  );
}

function TopBar({ title }) {
  const { unit, role, experiment } = useKiosk();
  const [sheetOpen, setSheetOpen] = useState(false);
  const unjoined = role === "unjoined";

  return (
    <header className="topbar">
      <h1 className="topbar-title truncate">{title}</h1>
      <span className="unit-name">
        <Icon name="pioreactor" />
        <span className="truncate">{unit}</span>
      </span>
      {!unjoined && (
        <button type="button" className="exp-chip" onClick={() => setSheetOpen(true)}>
          <span className="pill">
            <Icon name="experiment" />
            <span className="truncate">
              {experiment === undefined ? "Experiment..." : experiment === null ? "Not assigned" : experiment}
            </span>
          </span>
        </button>
      )}
      {sheetOpen && <ExperimentSheet onClose={() => setSheetOpen(false)} />}
    </header>
  );
}

// One line under the top bar when this unit's place in the cluster needs
// attention. Tapping it opens System, which has the details and the actions.
function StatusBanner() {
  const { role, leaderHostname, leaderReachable, worker } = useKiosk();

  let message = null;
  if (role === "unjoined") {
    message = "This Pioreactor isn't in a cluster. Add it from a leader's screen or web interface.";
  } else if (role === "worker" && leaderReachable === false) {
    message = `Can't reach the leader, ${leaderHostname}. Activities keep running, and you can still control them here.`;
  } else if (role === "worker" && worker === null) {
    message = `${leaderHostname} doesn't list this Pioreactor. Add it again from the leader, or leave its cluster.`;
  } else if (worker && !worker.is_active) {
    message = "This Pioreactor is inactive. Activities can't be started.";
  }
  if (!message) return null;

  return (
    <button type="button" className="status-banner" onClick={() => navigate("system")}>
      <span className="grow">{message}</span>
      <Icon name="forward" />
    </button>
  );
}

export default function KioskApp() {
  const { isLeader } = useKiosk();
  const page = usePage();
  const pages = PAGES.filter((item) => isLeader || !item.leaderOnly);
  const current = pages.find((item) => item.page === page || item.also?.includes(page)) || pages[0];
  const { Component } = current;

  return (
    <div className="app">
      <Rail pages={pages} active={current.page} />
      <main className="main">
        <TopBar title={current.label} />
        <StatusBanner />
        <Component />
      </main>
    </div>
  );
}
