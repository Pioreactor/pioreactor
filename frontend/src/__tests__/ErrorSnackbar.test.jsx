import React from "react";
import { act, render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const mockSubscribeToTopic = jest.fn();
const mockUnsubscribeFromTopic = jest.fn();
const mockEnqueueSnackbar = jest.fn();
const mockCloseSnackbar = jest.fn();
let mockSnackbarId = 0;

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({
    client: {},
    subscribeToTopic: mockSubscribeToTopic,
    unsubscribeFromTopic: mockUnsubscribeFromTopic,
  }),
}));

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: () => ({
    experimentMetadata: { experiment: "experiment-1" },
  }),
}));

jest.mock("notistack", () => ({
  useSnackbar: () => ({
    enqueueSnackbar: mockEnqueueSnackbar,
    closeSnackbar: mockCloseSnackbar,
  }),
}));

const { MemoryRouter } = require("react-router");
const ErrorSnackbar = require("../components/ErrorSnackbar").default;

function renderErrorSnackbar() {
  return render(
    <MemoryRouter>
      <ErrorSnackbar />
    </MemoryRouter>,
  );
}

function publishLog(handler, { unit = "unit-1", experiment = "experiment-1", task = "experiment_profile/1", level = "ERROR", message }) {
  act(() => {
    handler(
      `pioreactor/${unit}/${experiment}/logs/app/${level.toLowerCase()}`,
      Buffer.from(JSON.stringify({ task, level, message })),
      {},
    );
  });
}

describe("ErrorSnackbar", () => {
  beforeEach(() => {
    mockSnackbarId = 0;
    mockSubscribeToTopic.mockClear();
    mockUnsubscribeFromTopic.mockClear();
    mockCloseSnackbar.mockClear();
    mockEnqueueSnackbar.mockImplementation((_message, _options) => {
      mockSnackbarId += 1;
      return `snackbar-${mockSnackbarId}`;
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  test("subscribes to error, warning, and notice log topics", () => {
    renderErrorSnackbar();

    expect(mockSubscribeToTopic).toHaveBeenCalledWith(
      [
        "pioreactor/+/experiment-1/logs/+/error",
        "pioreactor/+/experiment-1/logs/+/warning",
        "pioreactor/+/experiment-1/logs/+/notice",
        "pioreactor/+/$experiment/logs/+/error",
        "pioreactor/+/$experiment/logs/+/warning",
        "pioreactor/+/$experiment/logs/+/notice",
      ],
      expect.any(Function),
      "ErrorSnackbar",
    );
  });

  test("stacks different log alerts instead of replacing the previous alert", () => {
    renderErrorSnackbar();
    const handler = mockSubscribeToTopic.mock.calls[0][1];

    publishLog(handler, { message: "stirring is already running (job_id=2062). Skipping." });
    publishLog(handler, { level: "NOTICE", message: "Finished executing profile." });

    expect(mockEnqueueSnackbar).toHaveBeenCalledTimes(2);
    expect(mockEnqueueSnackbar.mock.calls[0][1]).toMatchObject({
      TransitionProps: { direction: "up" },
    });
    expect(mockCloseSnackbar).not.toHaveBeenCalled();
  });

  test("updates repeated alerts from the same unit without replacing the snackbar", () => {
    const { unmount } = renderErrorSnackbar();
    const handler = mockSubscribeToTopic.mock.calls[0][1];

    publishLog(handler, { message: "stirring is already running (job_id=2062). Skipping." });
    expect(mockEnqueueSnackbar).toHaveBeenCalledTimes(1);

    const firstCallOptions = mockEnqueueSnackbar.mock.calls[0][1];
    render(<MemoryRouter>{firstCallOptions.content("snackbar-1")}</MemoryRouter>);
    expect(screen.queryByText(/Repeated/)).not.toBeInTheDocument();

    publishLog(handler, { message: "stirring is already running (job_id=2062). Skipping." });

    expect(mockEnqueueSnackbar).toHaveBeenCalledTimes(1);
    expect(mockCloseSnackbar).not.toHaveBeenCalled();
    expect(screen.getByText(/Repeated 2x/)).toBeInTheDocument();
    expect(screen.getByText(/experiment_profile\/1 failed in unit-1/)).not.toHaveTextContent("Repeated");

    unmount();
  });

  test("does not deduplicate the same alert from a different unit", () => {
    renderErrorSnackbar();
    const handler = mockSubscribeToTopic.mock.calls[0][1];

    publishLog(handler, { unit: "unit-1", message: "stirring is already running. Skipping." });
    publishLog(handler, { unit: "unit-2", message: "stirring is already running. Skipping." });

    expect(mockEnqueueSnackbar).toHaveBeenCalledTimes(2);
    expect(mockCloseSnackbar).not.toHaveBeenCalled();
  });
});
