import Stack from "@mui/material/Stack";
import { TimeFormatSwitch, TimeWindowSwitch } from "./TimeControls";

// The toggles wrap among themselves; the settings control stays on the first row.
export default function ChartControlsRow({ timeWindow, setTimeWindow, timeScale, setTimeScale, settingsControl }) {
  return (
    <Stack direction="row" sx={{ alignItems: "flex-start", gap: 1 }}>
      <Stack direction="row" sx={{ alignItems: "center", flexWrap: "wrap", gap: 1, flex: 1, minWidth: 0, minHeight: 44 }}>
        <TimeWindowSwitch setTimeWindow={setTimeWindow} timeWindow={timeWindow}/>
        <TimeFormatSwitch setTimeScale={setTimeScale} timeScale={timeScale}/>
      </Stack>
      {settingsControl}
    </Stack>
  );
}
