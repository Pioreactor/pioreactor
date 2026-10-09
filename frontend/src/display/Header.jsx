import { navigate, useDisplay } from "./context";
import { useNow } from "./hooks";
import { Icon } from "./ui";

export function formatElapsed(createdAt, now) {
  const start = Date.parse(createdAt);
  if (!Number.isFinite(start)) return "";
  const hours = Math.max(0, (now - start) / 3600000);
  if (hours < 48) return `${hours.toFixed(1)} h`;
  return `${Math.floor(hours / 24)} d ${Math.floor(hours % 24)} h`;
}

function ExperimentChip() {
  const { experimentMetadata } = useDisplay();
  const now = useNow(60000);
  const name = experimentMetadata?.experiment;
  return (
    <button className="exp-chip" onClick={() => navigate("experiment")} aria-label="Experiment details">
      <Icon name="experiment" />
      <span className="truncate">{name || "No experiment"}</span>
      {name && <span className="muted num">{formatElapsed(experimentMetadata.created_at, now)}</span>}
    </button>
  );
}

// One bar per screen: back button, title, screen actions, and the current experiment.
export default function Header({ title, subtitle, onBack, backLabel = "Back", actions, showExperiment = true }) {
  return (
    <header className="topbar">
      {onBack && (
        <button className="btn ghost icon-only" onClick={onBack} aria-label={backLabel}>
          <Icon name="back" />
        </button>
      )}
      <h1 className="topbar-title truncate">
        {title}
        {subtitle && <span className="muted topbar-sub"> {subtitle}</span>}
      </h1>
      {actions}
      {showExperiment && <ExperimentChip />}
    </header>
  );
}
