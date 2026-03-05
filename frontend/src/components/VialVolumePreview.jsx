import React, { useId } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

const VIAL_BODY_TOP_Y = 5.96;
const VIAL_BODY_BOTTOM_Y = 19.44;
const STROKEWIDTH=1.2
const VIAL_BODY_HEIGHT = VIAL_BODY_BOTTOM_Y - VIAL_BODY_TOP_Y - 2 * STROKEWIDTH/2;

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

  const liquidFraction = clamp(initialVolume / maxVolume, 0, 1);
  const tubeFraction = clamp(maxWorkingVolume / maxVolume, 0, 1);
  const liquidHeight = VIAL_BODY_HEIGHT * liquidFraction;
  const liquidY = VIAL_BODY_BOTTOM_Y - liquidHeight - STROKEWIDTH/2;
  const tubeBottomY = VIAL_BODY_BOTTOM_Y - VIAL_BODY_HEIGHT * tubeFraction - STROKEWIDTH/2;

  return (
    <Box sx={{ mt: 1, mb: 1, textAlign: "center" }}>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="-0.46 -0.6 12.23 20.64"
        width="80"
        height="80"
        aria-label="Dynamic vial volume preview"
        style={{ color: "#464646" }}
      >
        <defs>
          <clipPath id={clipPathId}>
            <path d="M0.17 5.96L0.14 19.44H11.17V5.81L0.18 5.97Z" />
          </clipPath>
        </defs>

        <rect
          x="0.14"
          y={liquidY}
          width="11.03"
          height={liquidHeight}
          fill="#e0d0b5"
          clipPath={`url(#${clipPathId})`}
        />

        <rect
          x="3.47"
          y="17.2"
          width="4.15"
          height="0.9"
          rx="0.4"
          fill="currentColor"
          stroke="none"
          clipPath={`url(#${clipPathId})`}
        />


        <rect
          x="0.86"
          y="0.5"
          width="9.61"
          height="3.0"
          fill="currentColor"
          stroke="currentColor"
          strokeWidth={STROKEWIDTH}
          strokeLinejoin="round"
        />

        <rect
          x="0.14"
          y="5.81"
          width="11.03"
          height="13.63"
          fill="none"
          stroke="currentColor"
          strokeWidth={STROKEWIDTH}
          strokeLinecap="round"
          strokeLinejoin="round"
        />


        <rect
          x="0.86"
          y="0.5"
          width="9.61"
          height="3.0"
          fill="currentColor"
          stroke="currentColor"
          strokeWidth={STROKEWIDTH}
          strokeLinejoin="round"
        />
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
