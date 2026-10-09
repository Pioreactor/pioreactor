import { AsyncButton, useToast } from "../ui";
import { EditField } from "../Keyboard";
import { fmt, parsePayload } from "../values";
import { runPioreactorJob } from "../../utils/jobs";

const CHANNELS = ["A", "B", "C", "D"];
const PRESETS = [0, 5, 10, 25, 50, 100];

export default function LedPanel({ unit, experiment, get }) {
  const toast = useToast();
  const intensities = parsePayload(get("leds", "intensity"));
  const current = intensities && typeof intensities === "object" ? intensities : {};

  const setIntensity = (channels, value) =>
    runPioreactorJob(unit, experiment, "led_intensity", [], {
      ...Object.fromEntries(channels.map((channel) => [channel, value])),
      source_of_event: "UI",
    });

  const allOff = async () => {
    await setIntensity(CHANNELS, 0);
    toast("Turning all LEDs off...");
  };

  return (
    <>
      <div className="section-title">LED intensity</div>
      <div className="grid-4">
        {CHANNELS.map((channel) => (
          <div className="card action-card" key={channel}>
            <h3>
                Channel {channel}
            </h3>
            <EditField
              className="wide"
              label="Intensity"
              value={fmt(current[channel] ?? null)}
              unit="%"
              min={0}
              max={100}
              allowNegative={false}
              presets={PRESETS}
              placeholder="Off"
              onCommit={(value) => setIntensity([channel], value)}
            />
          </div>
        ))}
      </div>
      <div className="btn-row" style={{ marginTop: "0.75rem" }}>
        <AsyncButton className="btn" onClick={allOff}>
          Turn all LEDs off
        </AsyncButton>
      </div>
    </>
  );
}
