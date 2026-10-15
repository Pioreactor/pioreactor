import { useKiosk } from "../context";
import { navigate, usePage } from "../router";
import { Segmented } from "../ui";
import Camera from "./Camera";
import Charts from "./Charts";

const TABS = [
  { value: "charts", label: "Charts" },
  { value: "camera", label: "Camera" },
];

// The culture in this vial over time: charts, and camera snapshots when the
// camera is enabled in config. Without a camera there are no tabs, only Charts.
export default function Culture() {
  const { config } = useKiosk();
  const page = usePage();
  const cameraEnabled = config.camera?.enabled === "1";
  const tab = cameraEnabled && page === "camera" ? "camera" : "charts";
  const tabs = cameraEnabled ? (
    <Segmented label="Culture section" options={TABS} value={tab} onChange={navigate} />
  ) : null;

  return tab === "camera" ? <Camera tabs={tabs} /> : <Charts tabs={tabs} />;
}
