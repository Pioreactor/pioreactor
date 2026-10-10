import { useState } from "react";
import { useKiosk } from "./context";
import { Icon } from "./icons";
import { navigate, usePage } from "./router";
import ExperimentSheet from "./ExperimentSheet";
import Activities from "./pages/Activities";
import Calibrations from "./pages/Calibrations";
import Charts from "./pages/Charts";
import Logs from "./pages/Logs";
import System from "./pages/System";

// Control (the Activities page) also owns /k/dosing and /k/leds, its other tabs.
const PAGES = [
  { page: "", label: "Control", icon: "control", Component: Activities, also: ["dosing", "leds"] },
  { page: "charts", label: "Charts", icon: "chart", Component: Charts },
  { page: "calibrations", label: "Calibrations", icon: "calibration", Component: Calibrations },
  { page: "logs", label: "Logs", icon: "logs", Component: Logs },
  { page: "system", label: "System", icon: "system", Component: System },
];

function Rail({ active }) {
  return (
    <nav className="rail" aria-label="Pages">
      {PAGES.map((item) => (
        <button
          type="button"
          key={item.page}
          className={`rail-item ${active === item.page ? "active" : ""}`}
          aria-current={active === item.page ? "page" : undefined}
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
  const { unit, experiment } = useKiosk();
  const [sheetOpen, setSheetOpen] = useState(false);

  return (
    <header className="topbar">
      <h1 className="topbar-title truncate">{title}</h1>
      <span className="unit-name">
        <Icon name="pioreactor" />
        <span className="truncate">{unit}</span>
      </span>
      <button type="button" className="exp-chip" onClick={() => setSheetOpen(true)}>
        <span className="pill">
          <Icon name="experiment" />
          <span className="truncate">
            {experiment === undefined ? "Experiment..." : experiment === null ? "Not assigned" : experiment}
          </span>
        </span>
      </button>
      {sheetOpen && <ExperimentSheet onClose={() => setSheetOpen(false)} />}
    </header>
  );
}

export default function KioskApp() {
  const page = usePage();
  const current = PAGES.find((item) => item.page === page || item.also?.includes(page)) || PAGES[0];
  const { Component } = current;

  return (
    <div className="app">
      <Rail active={current.page} />
      <main className="main">
        <TopBar title={current.label} />
        <Component />
      </main>
    </div>
  );
}
