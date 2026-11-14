import React from "react";
import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Typography from "@mui/material/Typography";
import CheckIcon from "@mui/icons-material/Check";
import useChartTheme from "../theme/useChartTheme";
import { unitColorChoices } from "../utils/color";

const SWATCH_SIZE = 28;

const ringSx = (style) => ({ outline: `2px ${style}`, outlineColor: "text.primary", outlineOffset: "2px" });

// chosenColor is null when the unit uses its automatic color.
export default function UnitColorPicker({ chosenColor, automaticColor, onChange }) {
  const chartTheme = useChartTheme();

  return (
    <Box>
      <Box
        role="group"
        aria-label="Line color"
        sx={{ display: "grid", gridTemplateColumns: `repeat(8, ${SWATCH_SIZE}px)`, gap: 1.25, p: 0.5 }}
      >
        {unitColorChoices.map((color) => {
          const isChosen = chosenColor === color;
          return (
            <ButtonBase
              key={color}
              disableRipple
              aria-label={color}
              aria-pressed={isChosen}
              onClick={() => onChange(color)}
              sx={{
                width: SWATCH_SIZE,
                height: SWATCH_SIZE,
                borderRadius: "50%",
                color: "common.white",
                backgroundColor: chartTheme.seriesColor(color),
                ...(isChosen ? ringSx("solid") : {}),
                ...(!chosenColor && automaticColor === color ? ringSx("dashed") : {}),
                "&.Mui-focusVisible": ringSx("solid"),
              }}
            >
              {isChosen && <CheckIcon sx={{ fontSize: 18 }} />}
            </ButtonBase>
          );
        })}
      </Box>
      <ButtonBase
        disableRipple
        aria-pressed={!chosenColor}
        onClick={() => onChange(null)}
        sx={{ mt: 1, gap: 1, px: 0.5, py: 0.25, borderRadius: 1, "&.Mui-focusVisible": { outline: "2px solid", outlineColor: "primary.main" } }}
      >
        <Box
          sx={{
            width: 20,
            height: 20,
            borderRadius: "50%",
            border: "2px dashed",
            borderColor: "text.secondary",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            ...(!chosenColor ? ringSx("solid") : {}),
          }}
        >
          {!chosenColor && <CheckIcon sx={{ fontSize: 14, color: "text.primary" }} />}
        </Box>
        <Typography variant="body2">Automatic</Typography>
      </ButtonBase>
    </Box>
  );
}
