import { createChartHistoryQueue } from "../utils/chartHistoryQueue";

test("visible histories settle first, then pending charts are prioritized using their current positions", async () => {
  const frames = [];
  const frame = jest.spyOn(window, "requestAnimationFrame").mockImplementation((fn) => frames.push(fn));
  const queue = createChartHistoryQueue();
  const loadOrder = [];
  const at = (top) => ({ getBoundingClientRect: () => ({ top, bottom: top + 200 }) });
  let finishVisible;
  try {
    queue(at(2000), async () => loadOrder.push("lower"));
    const scrolledIntoView = at(3000);
    queue(scrolledIntoView, async () => { loadOrder.push("scrolled"); throw Error("history failed"); });
    const cancel = queue(at(0), async () => loadOrder.push("removed"));
    cancel();
    queue(at(0), () => {
      loadOrder.push("visible");
      return new Promise((resolve) => { finishVisible = resolve; });
    });
    const batch = frames.shift()();
    expect(loadOrder).toEqual(["visible"]);
    expect(frames).toHaveLength(0);
    scrolledIntoView.getBoundingClientRect = at(0).getBoundingClientRect;
    finishVisible();
    await batch;
    await frames.shift()();
    await frames.shift()();
    expect(loadOrder).toEqual(["visible", "scrolled", "lower"]);
    expect(frames).toHaveLength(0);
  } finally {
    frame.mockRestore();
  }
});
