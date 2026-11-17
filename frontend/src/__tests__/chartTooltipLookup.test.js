import { VoronoiHelpers } from "victory";
import { createTooltipLookup } from "../components/ChartTooltipContainer";

function scale(max) {
  return Object.assign((v) => v * max / 10, { domain: () => [0, 10], range: () => [0, max] });
}

test("reuses the lookup between moves, preserves coincident points, and rebuilds after resizing", () => {
  const props = {
    data: [{ _x: 1, _y: 2 }, { _x: 1, _y: 2 }, { _x: 8, _y: 9 }],
    domain: { x: [0, 10], y: [0, 10] },
    scale: { x: scale(100), y: scale(100) },
  };
  const lookup = createTooltipLookup();
  const getData = jest.spyOn(VoronoiHelpers, "getDatasets");
  try {
    expect(lookup(props, { x: 11, y: 19 }).map((d) => d.eventKey)).toEqual([0, 1]);
    expect(lookup(props, { x: 75, y: 85 }).map((d) => d.eventKey)).toEqual([2]);
    expect(getData).toHaveBeenCalledTimes(1);
    props.scale.x = scale(500);
    expect(lookup(props, { x: 75, y: 85 }).map((d) => d.eventKey)).toEqual([0, 1]);
    expect(getData).toHaveBeenCalledTimes(2);
  } finally {
    getData.mockRestore();
  }
});
