import React from "react";
import Chip from "@mui/material/Chip";
import { Link } from "react-router";
import PluginIcon from "./PluginIcon";
import useLeaderHostname from "../hooks/useLeaderHostname";

// Plugins have no page of their own: the Chip opens the Plugins page for the given Pioreactor,
// or for the leader when the plugin isn't tied to one.
function PluginChip({ name, unit, sx }) {
  const leaderHostname = useLeaderHostname();
  const target = unit || leaderHostname;

  return (
    <Chip
      size="small"
      icon={<PluginIcon />}
      label={name}
      clickable
      component={Link}
      to={target ? `/plugins/${target}` : "/plugins"}
      sx={sx}
      data-plugin-name={name}
    />
  );
}

export default PluginChip;
