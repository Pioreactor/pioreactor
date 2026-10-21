import React, { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import PlayCircleOutlinedIcon from "@mui/icons-material/PlayCircleOutlined";
import { Link } from "react-router";
import PioreactorIcon from "./PioreactorIcon";
import CalibrationIcon from "./CalibrationIcon";
import EstimatorIcon from "./EstimatorIcon";
import PluginIcon from "./PluginIcon";
import { useExperiment } from "../providers/ExperimentContext";
import { parseLogMessage, splitTraceback } from "../utils/logMessage";

const ENTITY_ICONS = {
  pioreactor: PioreactorIcon,
  experiment: PlayCircleOutlinedIcon,
  calibration: CalibrationIcon,
  estimator: EstimatorIcon,
  plugin: PluginIcon,
};

// Compact enough to sit inside a line of 13px log text without stretching the row much.
const INLINE_CHIP_SX = {
  height: 20,
  fontSize: "inherit",
  verticalAlign: "middle",
  mx: 0.25,
  userSelect: "text",
  WebkitUserSelect: "text",
  "& .MuiChip-icon": {
    fontSize: 14,
    userSelect: "none",
    WebkitUserSelect: "none",
  },
  "& .MuiChip-label": {
    px: 0.75,
    userSelect: "text",
    WebkitUserSelect: "text",
  },
};

let clusterUnitsPromise = null;

function fetchClusterUnits() {
  if (clusterUnitsPromise === null) {
    clusterUnitsPromise = fetch("/api/workers")
      .then((response) => response.json())
      .then((workers) => new Set(workers.map((worker) => worker.pioreactor_unit)))
      .catch(() => {
        clusterUnitsPromise = null;
        return new Set();
      });
  }
  return clusterUnitsPromise;
}

// Cluster units, fetched once per page load and shared by every log table.
export function useClusterUnits() {
  const [units, setUnits] = useState(() => new Set());

  useEffect(() => {
    let cancelled = false;
    fetchClusterUnits().then((fetchedUnits) => {
      if (!cancelled) {
        setUnits(fetchedUnits);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return units;
}

function EntityChip({ type, label, unit, device }) {
  const { allExperiments, selectExperiment } = useExperiment() ?? {};
  const Icon = ENTITY_ICONS[type];
  const dataProps = {
    pioreactor: { "data-pioreactor-unit": label },
    experiment: { "data-experiment-name": label },
    calibration: { "data-calibration-name": label },
    estimator: { "data-estimator-name": label },
    plugin: { "data-plugin-name": label },
  }[type];

  if (type === "pioreactor") {
    return (
      <Chip
        size="small"
        icon={<Icon />}
        label={label}
        clickable
        component={Link}
        to={`/pioreactors/${label}`}
        sx={INLINE_CHIP_SX}
        {...dataProps}
      />
    );
  }

  // Experiments have no URL of their own: like the Experiments page, select the experiment and open its overview.
  if (type === "experiment" && allExperiments?.some((experiment) => experiment.experiment === label)) {
    return (
      <Chip
        size="small"
        icon={<Icon />}
        label={label}
        clickable
        component={Link}
        to="/overview"
        onClick={() => selectExperiment(label)}
        sx={INLINE_CHIP_SX}
        {...dataProps}
      />
    );
  }

  if (type === "calibration" && unit && device) {
    return (
      <Chip
        size="small"
        icon={<Icon />}
        label={label}
        clickable
        component={Link}
        to={`/calibrations/${encodeURIComponent(unit)}/${encodeURIComponent(device)}/${encodeURIComponent(label)}`}
        sx={INLINE_CHIP_SX}
        {...dataProps}
      />
    );
  }

  // Plugins have no page of their own: open the Plugins page for the Pioreactor that logged the message.
  if (type === "plugin" && unit) {
    return (
      <Chip
        size="small"
        icon={<Icon />}
        label={label}
        clickable
        component={Link}
        to={`/plugins/${unit}`}
        sx={INLINE_CHIP_SX}
        {...dataProps}
      />
    );
  }

  return <Chip size="small" icon={<Icon />} label={label} sx={INLINE_CHIP_SX} {...dataProps} />;
}

const textIcon = { verticalAlign: "middle", margin: "0px 3px" };

function MessageSegments({ text, units, experiment, unit }) {
  const segments = useMemo(
    () => parseLogMessage(text, { units, experiment }),
    [text, units, experiment]
  );

  return segments.map((segment, index) => {
    if (segment.type === "text") {
      return <React.Fragment key={index}>{segment.text}</React.Fragment>;
    }
    if (segment.type === "code") {
      return (
        <Box key={index} component="code" sx={{ fontFamily: "monospace", fontSize: "0.95em" }}>
          {segment.text}
        </Box>
      );
    }
    return <EntityChip key={index} type={segment.type} label={segment.text} unit={unit} device={segment.device} />;
  });
}

function TracebackToggle({ traceback }) {
  const [open, setOpen] = useState(false);
  const ToggleIcon = open ? ExpandLessIcon : ExpandMoreIcon;

  return (
    <>
      <Box>
        <Button
          size="small"
          onClick={() => setOpen((isOpen) => !isOpen)}
          aria-expanded={open}
          sx={{ p: 0, minWidth: 0, fontSize: "inherit" }}
        >
          <ToggleIcon fontSize="small" sx={textIcon} /> {open ? "Hide traceback" : "Show traceback"}
        </Button>
      </Box>
      <Collapse in={open} unmountOnExit>
        <Box
          component="pre"
          sx={{
            m: 0,
            mt: 0.5,
            p: 1,
            fontFamily: "monospace",
            fontSize: 12,
            whiteSpace: "pre",
            overflowX: "auto",
            maxWidth: "100%",
            bgcolor: "action.hover",
            borderRadius: 1,
          }}
        >
          {traceback}
        </Box>
      </Collapse>
    </>
  );
}

// Renders a log message with entity Chips. An appended traceback is reduced to its exception line,
// with the full traceback behind a toggle, or omitted where there is no room for it (showTraceback={false}).
function LogMessage({ message, units, experiment, unit, showTraceback = true }) {
  const { summary, exceptionLine, traceback } = useMemo(() => splitTraceback(message), [message]);
  const segmentProps = { units, experiment, unit };

  if (traceback === null) {
    return <MessageSegments text={summary} {...segmentProps} />;
  }

  return (
    <>
      {summary && <MessageSegments text={summary} {...segmentProps} />}
      {exceptionLine && (
        <Box component="span" sx={{ display: "block", fontFamily: "monospace", fontSize: "0.95em" }}>
          <MessageSegments text={exceptionLine} {...segmentProps} />
        </Box>
      )}
      {showTraceback && <TracebackToggle traceback={traceback} />}
    </>
  );
}

export default LogMessage;
