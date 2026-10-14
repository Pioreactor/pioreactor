import React, { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import PlayCircleOutlinedIcon from "@mui/icons-material/PlayCircleOutlined";
import { Link } from "react-router";
import PioreactorIcon from "./PioreactorIcon";
import CalibrationIcon from "./CalibrationIcon";
import EstimatorIcon from "./EstimatorIcon";
import { parseLogMessage } from "../utils/logMessage";

const ENTITY_ICONS = {
  pioreactor: PioreactorIcon,
  experiment: PlayCircleOutlinedIcon,
  calibration: CalibrationIcon,
  estimator: EstimatorIcon,
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

function EntityChip({ type, label }) {
  const Icon = ENTITY_ICONS[type];
  const dataProps = {
    pioreactor: { "data-pioreactor-unit": label },
    experiment: { "data-experiment": label },
    calibration: { "data-calibration-name": label },
    estimator: { "data-estimator-name": label },
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

  return <Chip size="small" icon={<Icon />} label={label} sx={INLINE_CHIP_SX} {...dataProps} />;
}

function LogMessage({ message, units, experiment }) {
  const segments = useMemo(
    () => parseLogMessage(message, { units, experiment }),
    [message, units, experiment]
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
    return <EntityChip key={index} type={segment.type} label={segment.text} />;
  });
}

export default LogMessage;
