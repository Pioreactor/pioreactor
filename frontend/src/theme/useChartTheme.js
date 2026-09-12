import { useColorScheme, lighten } from "@mui/material/styles";
import { VictoryTheme } from "victory";
import { darkColors } from "./colors";

const material = VictoryTheme.material;
const darkTheme = {
  ...material,
  axis: {
    ...material.axis,
    style: {
      ...material.axis.style,
      axis: { ...material.axis.style.axis, stroke: "#777583" },
      grid: { ...material.axis.style.grid, stroke: "#41424d" },
      ticks: { ...material.axis.style.ticks, stroke: "#777583" },
      tickLabels: { ...material.axis.style.tickLabels, fill: darkColors.textSecondary },
      axisLabel: { ...material.axis.style.axisLabel, fill: darkColors.textSecondary },
    },
  },
  legend: {
    ...material.legend,
    style: {
      ...material.legend.style,
      labels: { ...material.legend.style.labels, fill: darkColors.textSecondary },
    },
  },
};

const light = {
  theme: material,
  surface: "white",
  text: "#333",
  axisLabel: "grey",
  seriesColor: (color) => color,
};
const dark = {
  theme: darkTheme,
  surface: darkColors.surface,
  text: darkColors.text,
  axisLabel: darkColors.textSecondary,
  // Preserve hue and series identity while lifting dark lines off the canvas.
  seriesColor: (color) => color && /^(#[\da-f]{3,8}$|rgba?\()/i.test(color)
    ? lighten(color, 0.35)
    : color,
};

export default function useChartTheme() {
  const { mode, systemMode } = useColorScheme();
  return (mode === "system" ? systemMode : mode) === "dark" ? dark : light;
}
