import React from "react";
import { act, cleanup, render } from "@testing-library/react";

const mockSubscribeToTopic = jest.fn();
const mockUnsubscribeFromTopic = jest.fn();
const mockClient = {};

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({
    client: mockClient,
    subscribeToTopic: mockSubscribeToTopic,
    unsubscribeFromTopic: mockUnsubscribeFromTopic,
  }),
}));

const BioreactorDiagram = require("../components/BioreactorDiagram").default;
const {
  getBioreactorTubeLayout,
  getPwmDutyCyclesByLoad,
} = require("../components/bioreactorDiagramModel");

const config = {
  PWM: {
    1: "stirring",
    2: "media",
    5: "heating",
  },
  bioreactor: {
    initial_volume_ml: 14,
    efflux_tube_volume_ml: 18,
  },
};

describe("BioreactorDiagram model", () => {
  test("maps active GPIO pins to configured load names", () => {
    expect(getPwmDutyCyclesByLoad(
      { 12: 35, 13: 20 },
      { 2: "media", 4: "air_bubbler" },
    )).toEqual({ air_bubbler: 35, media: 20 });
  });

  test.each([
    ["media", "media"],
    ["alt_media", "alt-media"],
    ["waste", "efflux"],
  ])("labels the $load tube only when configured", (load, expectedLabel) => {
    const layout = getBioreactorTubeLayout({
      bioreactor: { x: 100, y: 65, width: 200, height: 400 },
      size: 20,
      volume: 14,
      maxVolume: 20,
      pwmConfig: { 2: load },
    });
    const pumpTubes = layout.tubes.filter(tube => ["media", "alt_media", "waste"].includes(tube.id));

    expect(pumpTubes.find(tube => tube.id === load).label).toBe(expectedLabel);
    expect(pumpTubes.filter(tube => tube.id !== load).every(tube => tube.label === "")).toBe(true);
  });

  test.each([
    [20, 400, 14],
    [40, 500, 20],
  ])("places a %i mL air stone below the liquid surface and inside the vial", (size, height, volume) => {
    const bioreactor = { x: 100, y: 65, width: 200, height };
    const layout = getBioreactorTubeLayout({
      bioreactor,
      size,
      volume,
      maxVolume: size,
      pwmConfig: { 4: "air_bubbler" },
    });
    const airTube = layout.tubes.find(tube => tube.id === "air");

    expect(airTube.label).toBe("air-bubbler");
    expect(airTube.load).toBe("air_bubbler");
    expect(airTube.tipY).toBeGreaterThan(layout.liquidSurfaceY);
    expect(airTube.airStone.y + airTube.airStone.height).toBeLessThan(
      bioreactor.y + bioreactor.height,
    );
  });

  test("leaves the spare tube unchanged without the air-bubbler plugin", () => {
    const bioreactor = { x: 100, y: 65, width: 200, height: 400 };
    const layout = getBioreactorTubeLayout({
      bioreactor,
      size: 20,
      volume: 14,
      maxVolume: 20,
    });
    const airTube = layout.tubes.find(tube => tube.id === "air");

    expect(airTube.label).toBe("");
    expect(airTube.load).toBeNull();
    expect(airTube.airStone).toBeUndefined();
    expect(airTube.tipY).toBe(112);
  });
});

function renderDiagram(props = {}) {
  return render(
    <BioreactorDiagram
      experiment="experiment-1"
      unit="unit-1"
      config={config}
      size={20}
      {...props}
    />,
  );
}

describe("BioreactorDiagram SVG", () => {
  let originalCancelAnimationFrame;
  let originalRequestAnimationFrame;
  let originalMatchMedia;
  let frames;
  let nextFrameId;

  beforeEach(() => {
    originalRequestAnimationFrame = window.requestAnimationFrame;
    originalCancelAnimationFrame = window.cancelAnimationFrame;
    originalMatchMedia = window.matchMedia;
    frames = new Map();
    nextFrameId = 0;
    window.requestAnimationFrame = jest.fn(callback => {
      frames.set(++nextFrameId, callback);
      return nextFrameId;
    });
    window.cancelAnimationFrame = jest.fn(id => frames.delete(id));
    window.matchMedia = jest.fn(query => ({
      matches: false,
      media: query,
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
    }));
  });

  afterEach(() => {
    cleanup();
    window.requestAnimationFrame = originalRequestAnimationFrame;
    window.cancelAnimationFrame = originalCancelAnimationFrame;
    window.matchMedia = originalMatchMedia;
    jest.clearAllMocks();
  });

  function sendTelemetry(setting, payload) {
    act(() => {
      mockSubscribeToTopic.mock.calls[0][1](
        `pioreactor/unit-1/experiment-1/${setting}`,
        JSON.stringify(payload),
      );
    });
  }

  function advanceFrame(timestamp) {
    const [id, callback] = frames.entries().next().value;
    frames.delete(id);
    act(() => callback(timestamp));
  }

  test.each([[20, 510, 400], [40, 610, 500]])(
    "renders the %i mL geometry with the efflux tip aligned to its marker",
    (size, diagramHeight, vialHeight) => {
      const diagram = renderDiagram({size, liquidVolume: 10, maxVolume: 15});
      const svg = diagram.getByRole("img", {name: "Bioreactor diagram"});
      expect(svg.tagName.toLowerCase()).toBe("svg");
      expect(svg).toHaveAttribute("viewBox", `0 0 400 ${diagramHeight}`);
      expect(diagram.getByText("10 mL")).toBeInTheDocument();
      expect(diagram.getByText("15 mL")).toBeInTheDocument();
      const tube = svg.querySelector('[data-tube="waste"] rect');
      const marker = svg.querySelector('line[stroke-dasharray="4 3"]');
      const expectedTip = 65 + vialHeight * (1 - 15 / size);
      expect(Number(tube.getAttribute("y")) + Number(tube.getAttribute("height"))).toBe(expectedTip);
      expect(Number(marker.getAttribute("y1"))).toBe(expectedTip);
      expect(window.requestAnimationFrame).not.toHaveBeenCalled();
    },
  );

  test("animates only the stir bar, then resets and stops when stirring stops", () => {
    const diagram = renderDiagram();
    const svg = diagram.getByRole("img", {name: "Bioreactor diagram"});
    const stirBar = svg.querySelector('[data-part="stir-bar"]');
    const liquid = svg.querySelector('rect[fill="#e0d0b5"]');
    const liquidBefore = liquid.outerHTML;
    sendTelemetry("pwms/dc", {17: 10});
    advanceFrame(0);
    advanceFrame(100);
    expect(Number(stirBar.getAttribute("width"))).toBeLessThan(80);
    expect(Number(stirBar.getAttribute("width"))).toBeGreaterThanOrEqual(10);
    expect(Number(stirBar.getAttribute("x")) + Number(stirBar.getAttribute("width")) / 2).toBeCloseTo(200);
    expect(liquid.outerHTML).toBe(liquidBefore);

    // Unrelated telemetry must not restart the animation.
    const scheduledFrames = window.requestAnimationFrame.mock.calls.length;
    sendTelemetry("temperature_automation/temperature", {temperature: 31});
    expect(window.requestAnimationFrame).toHaveBeenCalledTimes(scheduledFrames);
    expect(window.cancelAnimationFrame).not.toHaveBeenCalled();

    sendTelemetry("pwms/dc", {17: 0});
    expect(stirBar).toHaveAttribute("width", "80");
    expect(stirBar).toHaveAttribute("x", "160");
    expect(frames.size).toBe(0);
    expect(svg.querySelector("desc")).toHaveTextContent("Stirring off");
  });

  test("cancels the animation and unsubscribes on unmount", () => {
    const diagram = renderDiagram();
    sendTelemetry("pwms/dc", {17: 10});
    advanceFrame(0);
    diagram.unmount();
    expect(frames.size).toBe(0);
    expect(mockUnsubscribeFromTopic).toHaveBeenCalledTimes(1);
    expect(mockUnsubscribeFromTopic).toHaveBeenCalledWith(
      mockSubscribeToTopic.mock.calls[0][0], "BioreactorDiagram",
    );
  });

  test("updates idle telemetry, liquid volume, and the liquid-pump warning without animation", () => {
    const diagram = renderDiagram();
    const svg = diagram.getByRole("img", {name: "Bioreactor diagram"});
    sendTelemetry("leds/intensity", {A: 30, B: 0, C: 0, D: 0});
    sendTelemetry("temperature_automation/temperature", {temperature: 31});
    sendTelemetry("growth_rate_calculating/od_filtered", {od_filtered: 0.8});
    sendTelemetry("pwms/dc", {13: 25, 18: 50});
    expect(diagram.getByText("Temp: 31°C")).toBeInTheDocument();
    expect(diagram.getByText("nOD: 0.8")).toBeInTheDocument();
    expect(diagram.getByText(/diagram above may not be an accurate/)).toBeInTheDocument();
    expect(svg.querySelector('[data-led="A"] rect')).toHaveAttribute("fill", "rgba(234, 188, 116, 0.5)");
    expect(svg.querySelector('[data-part="heater"] rect')).toHaveAttribute("fill", "#D8A0A2");
    expect(svg.querySelector('[data-tube="media"] rect')).toHaveAttribute("fill", "#EABC74");
    expect(svg.querySelectorAll("polyline").length).toBeGreaterThan(0);
    diagram.rerender(
      <BioreactorDiagram experiment="experiment-1" unit="unit-1" config={config} size={20} liquidVolume={15} />,
    );
    expect(diagram.getByText("15 mL")).toBeInTheDocument();
    expect(svg.querySelector('rect[fill="#e0d0b5"]')).toHaveAttribute("height", "300");
    sendTelemetry("pwms/dc", {});
    expect(diagram.queryByText(/diagram above may not be an accurate/)).not.toBeInTheDocument();
    expect(window.requestAnimationFrame).not.toHaveBeenCalled();
  });

  test("does not animate a non-finite RPM estimate", () => {
    renderDiagram();
    sendTelemetry("pwms/dc", {17: "not-a-number"});
    expect(window.requestAnimationFrame).not.toHaveBeenCalled();
  });

  test("honors reduced motion while still reporting stirring as on", () => {
    window.matchMedia.mockImplementation(query => ({
      matches: true, media: query, addEventListener: jest.fn(), removeEventListener: jest.fn(),
    }));
    const diagram = renderDiagram();
    sendTelemetry("pwms/dc", {17: 10});
    expect(window.requestAnimationFrame).not.toHaveBeenCalled();
    expect(diagram.getByRole("img").querySelector("desc")).toHaveTextContent("Stirring on");
  });

  test("highlights an installed air bubbler without showing the liquid-pump warning", () => {
    const diagram = renderDiagram({config: {...config, PWM: {...config.PWM, 4: "air_bubbler"}}});
    const svg = diagram.getByRole("img", {name: "Bioreactor diagram"});
    const airStone = svg.querySelector('[data-tube="air"] rect:last-child');
    expect(airStone).toHaveAttribute("fill", "#99999B");
    sendTelemetry("pwms/dc", {12: 35});
    expect(airStone).toHaveAttribute("fill", "#EABC74");
    expect(diagram.queryByText(/diagram above may not be an accurate/)).not.toBeInTheDocument();
  });
});
