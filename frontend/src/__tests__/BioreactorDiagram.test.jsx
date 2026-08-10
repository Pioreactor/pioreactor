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
  return {
    beginPath: jest.fn(),
    clearRect: jest.fn(),
    closePath: jest.fn(),
    fill: jest.fn(),
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
}

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
});
