import Header from "../Header";
import ChartView from "./ChartView";

export default function Charts() {
  return (
    <>
      <Header title="Charts" />
      <div className="content fill">
        <ChartView />
      </div>
    </>
  );
}
