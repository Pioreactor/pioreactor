import { EditField } from "../Keyboard";
import { useJobControl } from "../jobs";
import { AsyncButton, useToast } from "../ui";
import { fmt, parsePayload } from "../values";

const CHANNELS = ["A", "B", "C", "D"];
const PRESETS = [0, 5, 10, 25, 50, 100];

// A tab of Activities, which handles the no-experiment and offline cases.
export default function Leds({ get }) {
  const toast = useToast();
  const control = useJobControl();

  const intensities = parsePayload(get("leds", "intensity"));
  const current = intensities && typeof intensities === "object" ? intensities : {};

  const setIntensity = (channels, value) =>
    control.run("led_intensity", {
      options: { ...Object.fromEntries(channels.map((channel) => [channel, value])), source_of_event: "UI" },
    });

  return (
    <>
      <h2 className="section-title">LED intensity</h2>
      <div className="grid-4">
        {CHANNELS.map((channel) => (
          <div className="card" key={channel}>
            <h3>Channel {channel}</h3>
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
      <div className="btn-row spaced">
        <AsyncButton
          className="btn"
          onClick={async () => {
            await setIntensity(CHANNELS, 0);
            toast("Turning all LEDs off...");
          }}
        >
          Turn all LEDs off
        </AsyncButton>
      </div>
    </>
  );
}
