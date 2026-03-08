import React, { useId } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

const STROKEWIDTH = 1.2;
const BASE_MAX_VOLUME_ML = 20;
const SVG_WIDTH = 12.23;
const SVG_BASE_HEIGHT = 20.64;
const SVG_BASE_PIXEL_HEIGHT = 80;
const VIEWBOX_TOP_Y = -0.6;
const VIEWBOX_BOTTOM_PADDING = 0.6;

const CAP_X = 0.86;
const CAP_Y = 0.5;
const CAP_WIDTH = 9.61;
const CAP_HEIGHT = 3.0;

const VIAL_BODY_X = 0.14;
const VIAL_BODY_WIDTH = 11.03;
const VIAL_BODY_TOP_Y = 5.81;
const VIAL_BODY_BASE_OUTER_HEIGHT = 13.63;
const VIAL_BODY_BASE_INNER_HEIGHT = VIAL_BODY_BASE_OUTER_HEIGHT - STROKEWIDTH;

const STIR_BAR_X = 3.47;
const STIR_BAR_WIDTH = 4.15;
const STIR_BAR_HEIGHT = 0.9;
const STIR_BAR_BOTTOM_OFFSET = 2.24;

const clampMin = (value, min) => Math.max(value, min);

const asNumber = (value) => {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : null;
};

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));


function VialVolumePreview({
  initialVolumeMl,
  maxWorkingVolumeMl,
  maxVolumeMl,
}) {
  const clipPathId = useId();
  const initialVolume = asNumber(initialVolumeMl);
  const maxWorkingVolume = asNumber(maxWorkingVolumeMl);
  const maxVolume = asNumber(maxVolumeMl);

  if (
    initialVolume == null ||
    maxWorkingVolume == null ||
    maxVolume == null ||
    maxVolume <= 0
  ) {
    return null;
  }

  const bodyHeightScale = clampMin(maxVolume / BASE_MAX_VOLUME_ML, 1);
  const vialBodyOuterHeight = VIAL_BODY_BASE_OUTER_HEIGHT * bodyHeightScale;
  const vialBodyInnerHeight = VIAL_BODY_BASE_INNER_HEIGHT * bodyHeightScale;
  const vialBodyBottomY = VIAL_BODY_TOP_Y + vialBodyOuterHeight;
  const vialBodyInnerBottomY = vialBodyBottomY - STROKEWIDTH / 2;
  const stirBarY = vialBodyBottomY - STIR_BAR_BOTTOM_OFFSET;
  const viewBoxHeight = vialBodyBottomY - VIEWBOX_TOP_Y + VIEWBOX_BOTTOM_PADDING;
  const svgHeight = SVG_BASE_PIXEL_HEIGHT * (viewBoxHeight / SVG_BASE_HEIGHT);

  const liquidFraction = clamp(initialVolume / maxVolume, 0, 1);
  const tubeFraction = clamp(maxWorkingVolume / maxVolume, 0, 1);
  const liquidHeight = vialBodyInnerHeight * liquidFraction;
  const liquidY = vialBodyInnerBottomY - liquidHeight;
  const tubeBottomY = vialBodyInnerBottomY - vialBodyInnerHeight * tubeFraction;

  return (
    <Box sx={{ mt: 1, mb: 1, textAlign: "center" }}>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox={`-0.46 ${VIEWBOX_TOP_Y} ${SVG_WIDTH} ${viewBoxHeight}`}
        width="80"
        height={svgHeight}
        aria-label="Dynamic vial volume preview"
        style={{ color: "#464646" }}
      >
        <defs>
          <clipPath id={clipPathId}>
            <rect
              x={VIAL_BODY_X}
              y={VIAL_BODY_TOP_Y}
              width={VIAL_BODY_WIDTH}
              height={vialBodyOuterHeight}
            />
          </clipPath>
        </defs>

        <rect
          x={VIAL_BODY_X}
          y={liquidY}
          width={VIAL_BODY_WIDTH}
          height={liquidHeight}
          fill="#e0d0b5"
          clipPath={`url(#${clipPathId})`}
        />

        <rect
          x={STIR_BAR_X}
          y={stirBarY}
          width={STIR_BAR_WIDTH}
          height={STIR_BAR_HEIGHT}
          rx="0.4"
          fill="currentColor"
          stroke="none"
          clipPath={`url(#${clipPathId})`}
        />


        <rect
          x={CAP_X}
          y={CAP_Y}
          width={CAP_WIDTH}
          height={CAP_HEIGHT}
          fill="currentColor"
          stroke="currentColor"
          strokeWidth={STROKEWIDTH}
          strokeLinejoin="round"
        />

        <rect
          x={VIAL_BODY_X}
          y={VIAL_BODY_TOP_Y}
          width={VIAL_BODY_WIDTH}
          height={vialBodyOuterHeight}
          fill="none"
          stroke="currentColor"
          strokeWidth={STROKEWIDTH}
          strokeLinecap="round"
          strokeLinejoin="round"
        />


        <rect
          x={CAP_X}
          y={CAP_Y}
          width={CAP_WIDTH}
          height={CAP_HEIGHT}
          fill="currentColor"
          stroke="currentColor"
          strokeWidth={STROKEWIDTH}
          strokeLinejoin="round"
        />
        <line x1="0.86" y1={tubeBottomY} x2="10.47" y2={tubeBottomY} stroke="grey" strokeWidth={0.5} strokeDasharray="1,0.45" />
        <line x1="7.14" y1="0.00" x2="7.14" y2={tubeBottomY} stroke="currentColor" strokeWidth={STROKEWIDTH} />
        <line x1="4" y1="0.00" x2="4" y2="7" stroke="currentColor" strokeWidth={STROKEWIDTH} />

      </svg>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
        Initial vial preview
      </Typography>
    </Box>
  );
}

export default VialVolumePreview;
