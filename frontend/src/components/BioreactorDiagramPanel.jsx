import React, { useCallback, useEffect } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { useMQTT } from "../providers/MQTTContext";
import {
  getBioreactorConfirmedValue,
  getBioreactorSubscriptionTopics,
  parseNumericValue,
} from "../utils/bioreactor";
import BioreactorDiagram from "./BioreactorDiagram";

const DIAGRAM_BIOREACTOR_KEYS = ["current_volume_ml", "efflux_tube_volume_ml"];

export default function BioreactorDiagramPanel({
  unit,
  experiment,
  config,
  modelDetails,
  values,
  onValuesChange,
}) {
  const { client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const bioreactorValues = values || {};

  const hasDiagram = Boolean(
    modelDetails.model_name?.startsWith("pioreactor_20ml")
      || modelDetails.model_name?.startsWith("pioreactor_40ml")
  );

  const onBioreactorMessage = useCallback((topic, message) => {
    if (!topic || !message) {
      return;
    }

    const parts = topic.toString().split("/");
    const variableName = parts[4];
    const parsedValue = parseNumericValue(message.toString());
    if (!variableName || parsedValue === null) {
      return;
    }

    onValuesChange?.((previous) => ({
      ...previous,
      [variableName]: parsedValue,
    }));
  }, [onValuesChange]);

  useEffect(() => {
    if (!client || !unit || !experiment) {
      return undefined;
    }

    const topics = getBioreactorSubscriptionTopics(unit, experiment, DIAGRAM_BIOREACTOR_KEYS);
    subscribeToTopic(topics, onBioreactorMessage, "BioreactorDiagramPanel");

    return () => {
      unsubscribeFromTopic(topics, "BioreactorDiagramPanel");
    };
  }, [client, experiment, onBioreactorMessage, subscribeToTopic, unsubscribeFromTopic, unit]);

  if (!hasDiagram) {
    return (
      <Box sx={{ display: "flex", height: "100%", alignItems: "center", justifyContent: "center" }}>
        <Typography variant="body2" component="p" color="textSecondary">
          No diagram available for this model
        </Typography>
      </Box>
    );
  }

  return (
    <BioreactorDiagram
      key={`${unit}/${experiment}`}
      experiment={experiment}
      unit={unit}
      config={config}
      size={modelDetails.reactor_capacity_ml}
      liquidVolume={getBioreactorConfirmedValue(bioreactorValues, config, "current_volume_ml")}
      maxVolume={getBioreactorConfirmedValue(bioreactorValues, config, "efflux_tube_volume_ml")}
    />
  );
}
