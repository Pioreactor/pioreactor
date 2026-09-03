import React from "react";
import { act, render } from "@testing-library/react";

const mockSubscribeToTopic = jest.fn();
const mockUnsubscribeFromTopic = jest.fn();

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({
    client: {},
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

function makeCanvasContext() {
  const context = {
    beginPath: jest.fn(),
    clearRect: jest.fn(),
    closePath: jest.fn(),
    fill: jest.fn(() => context.fillStyles.push(context.fillStyle)),
    fillStyles: [],
    fillText: jest.fn(),
    lineTo: jest.fn(),
    measureText: jest.fn(() => ({ width: 10 })),
    moveTo: jest.fn(),
    quadraticCurveTo: jest.fn(),
    restore: jest.fn(),
    rotate: jest.fn(),
    save: jest.fn(),
    setLineDash: jest.fn(),
    stroke: jest.fn(),
    translate: jest.fn(),
  };
  return context;
}

describe("BioreactorDiagram model", () => {
  test("maps active GPIO pins to configured load names", () => {
    expect(getPwmDutyCyclesByLoad(
      { 12: 35, 13: 20 },
      { 2: "media", 4: "air_bubbler" },
    )).toEqual({ air_bubbler: 35, media: 20 });
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
      hasAirBubbler: true,
    });
    const airTube = layout.tubes.find(tube => tube.id === "air");

    expect(airTube.label).toBe("air_bubbler");
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
      hasAirBubbler: false,
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

describe("BioreactorDiagram animation", () => {
  let canvasContext;
  let getContextSpy;
  let originalCancelAnimationFrame;
  let originalRequestAnimationFrame;

  beforeEach(() => {
    canvasContext = makeCanvasContext();
    getContextSpy = jest
      .spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockReturnValue(canvasContext);

    originalRequestAnimationFrame = window.requestAnimationFrame;
    originalCancelAnimationFrame = window.cancelAnimationFrame;
    window.requestAnimationFrame = jest.fn(() => 1);
    window.cancelAnimationFrame = jest.fn();
  });

  afterEach(() => {
    getContextSpy.mockRestore();
    window.requestAnimationFrame = originalRequestAnimationFrame;
    window.cancelAnimationFrame = originalCancelAnimationFrame;
    jest.clearAllMocks();
  });

  test("draws once without scheduling an animation frame when RPM is absent", () => {
    renderDiagram();

    expect(canvasContext.clearRect).toHaveBeenCalledTimes(1);
    expect(window.requestAnimationFrame).not.toHaveBeenCalled();
    expect(canvasContext.fillText).toHaveBeenCalledWith("14 mL", 110, 155);
    expect(canvasContext.setLineDash).toHaveBeenCalledWith([2, 3]);
    expect(canvasContext.lineTo).toHaveBeenCalledWith(110, 185);
  });

  test("animates positive RPM and cancels the active frame on unmount", () => {
    const diagram = renderDiagram();
    const onMessage = mockSubscribeToTopic.mock.calls[0][1];

    act(() => {
      onMessage("pioreactor/unit-1/experiment-1/pwms/dc", '{"17": 10}');
    });

    expect(window.requestAnimationFrame).toHaveBeenCalledTimes(1);

    diagram.unmount();

    expect(window.cancelAnimationFrame).toHaveBeenCalledWith(1);
  });

  test("cancels positive-RPM animation and draws once when RPM becomes zero", () => {
    renderDiagram();
    const onMessage = mockSubscribeToTopic.mock.calls[0][1];

    act(() => {
      onMessage("pioreactor/unit-1/experiment-1/pwms/dc", '{"17": 10}');
    });

    act(() => {
      onMessage("pioreactor/unit-1/experiment-1/pwms/dc", '{"17": 0}');
    });

    expect(window.cancelAnimationFrame).toHaveBeenCalledWith(1);
    expect(window.requestAnimationFrame).toHaveBeenCalledTimes(1);
    expect(canvasContext.clearRect).toHaveBeenCalledTimes(2);
  });

  test("redraws changing diagram state while idle without scheduling frames", () => {
    const diagram = renderDiagram();
    const onMessage = mockSubscribeToTopic.mock.calls[0][1];

    const idleMessages = [
      ["pioreactor/unit-1/experiment-1/leds/intensity", '{"A": 40, "B": 0, "C": 0, "D": 0}'],
      ["pioreactor/unit-1/experiment-1/temperature_automation/temperature", '{"temperature": 31}'],
      ["pioreactor/unit-1/experiment-1/growth_rate_calculating/od_filtered", '{"od_filtered": 0.8}'],
      ["pioreactor/unit-1/experiment-1/pwms/dc", '{"13": 25, "18": 50}'],
    ];

    idleMessages.forEach(([topic, message], index) => {
      act(() => {
        onMessage(topic, message);
      });
      expect(canvasContext.clearRect).toHaveBeenCalledTimes(index + 2);
    });

    diagram.rerender(
      <BioreactorDiagram
        experiment="experiment-1"
        unit="unit-1"
        config={config}
        size={20}
        liquidVolume={15}
      />,
    );

    expect(canvasContext.clearRect).toHaveBeenCalledTimes(idleMessages.length + 2);
    expect(window.requestAnimationFrame).not.toHaveBeenCalled();
  });

  test("draws once without animation for a non-finite RPM estimate", () => {
    renderDiagram();
    const onMessage = mockSubscribeToTopic.mock.calls[0][1];

    act(() => {
      onMessage("pioreactor/unit-1/experiment-1/pwms/dc", '{"17": "not-a-number"}');
    });

    expect(canvasContext.clearRect).toHaveBeenCalledTimes(2);
    expect(window.requestAnimationFrame).not.toHaveBeenCalled();
  });

  test("highlights an installed air bubbler without showing the liquid-pump warning", () => {
    const diagram = renderDiagram({
      hasAirBubbler: true,
      config: {
        ...config,
        PWM: { ...config.PWM, 4: "air_bubbler" },
      },
    });
    const canvas = diagram.getByRole("img", { name: /air bubbler is off/i });
    const onMessage = mockSubscribeToTopic.mock.calls[0][1];

    expect(canvasContext.fillStyles).toContain("#99999B");
    expect(canvasContext.fillText).toHaveBeenCalledWith("air_bubbler", 0, 0);

    canvasContext.fillStyles.length = 0;
    act(() => {
      onMessage("pioreactor/unit-1/experiment-1/pwms/dc", '{"12": 35}');
    });

    expect(canvas).toHaveAccessibleName(/air bubbler is on/i);
    expect(canvasContext.fillStyles).toContain("#EABC74");
    expect(canvasContext.fillStyles).not.toContain("rgb(255, 244, 229)");
  });
});
