import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const mockSubscribeToTopic = jest.fn();
const mockUnsubscribeFromTopic = jest.fn();
const mockMqttClient = {};
let subscribedHandler = null;

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({
    client: mockMqttClient,
    subscribeToTopic: mockSubscribeToTopic,
    unsubscribeFromTopic: mockUnsubscribeFromTopic,
  }),
}));

jest.mock("../utils/config", () => ({
  getConfig: (setCallback) =>
    setCallback({
      "cluster.topology": {
        leader_hostname: "leader1",
      },
    }),
}));

jest.mock("react-showdown", () => ({
  __esModule: true,
  default: ({ markdown }) => <div>{markdown}</div>,
}));

const Updates = require("../Updates").default;
const { UpdateFromInternetAndConfirm } = require("../Updates");

describe("Updates page", () => {
  beforeEach(() => {
    subscribedHandler = null;
    mockSubscribeToTopic.mockImplementation((_topic, handler) => {
      subscribedHandler = handler;
    });
    mockUnsubscribeFromTopic.mockReset();

    global.fetch = jest.fn((url) => {
      if (url === "https://api.github.com/repos/pioreactor/pioreactor/releases/latest") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ tag_name: "26.3.10" }),
        });
      }

      if (url === "https://raw.githubusercontent.com/Pioreactor/pioreactor/master/CHANGELOG.md") {
        return Promise.resolve({
          ok: true,
          text: () => Promise.resolve("# Changelog"),
        });
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("shows the leader version from the leader monitor MQTT topic", async () => {
    render(<Updates title="Pioreactor ~ Updates" />);

    await waitFor(() => {
      expect(mockSubscribeToTopic).toHaveBeenCalledWith(
        "pioreactor/leader1/$experiment/monitor/versions",
        expect.any(Function),
        "UpdatesPageHeader-leader-version",
      );
    });

    await act(async () => {
      subscribedHandler(
        "pioreactor/leader1/$experiment/monitor/versions",
        { toString: () => JSON.stringify({ app: "26.3.0" }) },
      );
    });

    expect(screen.getByText("26.3.0")).toBeTruthy();
  });

  test("accepts a valid dropped release archive in the update dialog", async () => {
    const user = userEvent.setup();
    global.fetch = jest.fn((url) => {
      if (url === "https://api.github.com/repos/pioreactor/pioreactor/releases/latest") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ tag_name: "26.3.10" }),
        });
      }

      if (url === "https://raw.githubusercontent.com/Pioreactor/pioreactor/master/CHANGELOG.md") {
        return Promise.resolve({
          ok: true,
          text: () => Promise.resolve("# Changelog"),
        });
      }

      if (url === "/api/units") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ pioreactor_unit: "leader1" }]),
        });
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    render(<Updates title="Pioreactor ~ Updates" />);

    await user.click(screen.getByRole("button", { name: /update from zip file/i }));
    const dropTarget = await screen.findByText(/drop a/i);

    fireEvent.drop(dropTarget, {
      dataTransfer: {
        files: [new File(["zip"], "release_26.4.0.zip", { type: "application/zip" })],
      },
    });

    expect(await screen.findByText("release_26.4.0.zip")).toBeInTheDocument();
    expect(screen.queryByText(/not a valid release archive file/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update" })).toBeEnabled();
  });

  test("accepts a duplicate downloaded release archive filename in the update dialog", async () => {
    const user = userEvent.setup();
    global.fetch = jest.fn((url) => {
      if (url === "https://api.github.com/repos/pioreactor/pioreactor/releases/latest") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ tag_name: "26.3.10" }),
        });
      }

      if (url === "https://raw.githubusercontent.com/Pioreactor/pioreactor/master/CHANGELOG.md") {
        return Promise.resolve({
          ok: true,
          text: () => Promise.resolve("# Changelog"),
        });
      }

      if (url === "/api/units") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ pioreactor_unit: "leader1" }]),
        });
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    render(<Updates title="Pioreactor ~ Updates" />);

    await user.click(screen.getByRole("button", { name: /update from zip file/i }));
    const dropTarget = await screen.findByText(/drop a/i);

    fireEvent.drop(dropTarget, {
      dataTransfer: {
        files: [new File(["zip"], "release_26.4.0 (1).zip", { type: "application/zip" })],
      },
    });

    expect(await screen.findByText("release_26.4.0 (1).zip")).toBeInTheDocument();
    expect(screen.queryByText(/not a valid release archive file/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update" })).toBeEnabled();
  });

  test("shows an error for a filename that does not end in zip", async () => {
    const user = userEvent.setup();
    global.fetch = jest.fn((url) => {
      if (url === "https://api.github.com/repos/pioreactor/pioreactor/releases/latest") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ tag_name: "26.3.10" }),
        });
      }

      if (url === "https://raw.githubusercontent.com/Pioreactor/pioreactor/master/CHANGELOG.md") {
        return Promise.resolve({
          ok: true,
          text: () => Promise.resolve("# Changelog"),
        });
      }

      if (url === "/api/units") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ pioreactor_unit: "leader1" }]),
        });
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    render(<Updates title="Pioreactor ~ Updates" />);

    await user.click(screen.getByRole("button", { name: /update from zip file/i }));
    const dropTarget = await screen.findByText(/drop a/i);

    fireEvent.drop(dropTarget, {
      dataTransfer: {
        files: [new File(["zip"], "release_26.4.0.zip (1)", { type: "application/zip" })],
      },
    });

    expect(await screen.findByText(/not a valid release archive file/i)).toBeInTheDocument();
    expect(screen.queryByText("release_26.4.0.zip (1)")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update" })).toBeDisabled();
  });

  test("queues an internet update and reports success", async () => {
    const user = userEvent.setup();
    const onClose = jest.fn();
    const onSuccess = jest.fn();

    global.fetch = jest.fn((url) => {
      if (url === "/api/units") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ pioreactor_unit: "leader1" }]),
        });
      }

      if (url === "/api/system/update_next_version") {
        return Promise.resolve({ ok: true });
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    render(
      <UpdateFromInternetAndConfirm
        title="Update to next release?"
        description="Update from the internet."
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith("/api/units"));
    await user.click(screen.getByRole("button", { name: "Update" }));

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/system/update_next_version",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ units: "$broadcast" }),
        }),
      ),
    );
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  test("shows internet update failures and re-enables the update button", async () => {
    const user = userEvent.setup();

    global.fetch = jest.fn((url) => {
      if (url === "/api/units") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ pioreactor_unit: "leader1" }]),
        });
      }

      if (url === "/api/system/update_next_version") {
        return Promise.resolve({
          ok: false,
          status: 503,
          json: () => Promise.resolve({ error: "Leader cannot reach workers." }),
        });
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    render(
      <UpdateFromInternetAndConfirm
        title="Update to next release?"
        description="Update from the internet."
        onClose={() => {}}
        onSuccess={() => {}}
      />,
    );

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith("/api/units"));
    const updateButton = screen.getByRole("button", { name: "Update" });
    await user.click(updateButton);

    expect(await screen.findByText("Leader cannot reach workers.")).toBeInTheDocument();
    await waitFor(() => expect(updateButton).toBeEnabled());
  });

  test("keeps internet update pending until the request resolves", async () => {
    const user = userEvent.setup();
    let resolveUpdate;
    const updatePromise = new Promise((resolve) => {
      resolveUpdate = resolve;
    });

    global.fetch = jest.fn((url) => {
      if (url === "/api/units") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ pioreactor_unit: "leader1" }]),
        });
      }

      if (url === "/api/system/update_next_version") {
        return updatePromise;
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    render(
      <UpdateFromInternetAndConfirm
        title="Update to next release?"
        description="Update from the internet."
        onClose={() => {}}
        onSuccess={() => {}}
      />,
    );

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith("/api/units"));
    const updateButton = screen.getByRole("button", { name: "Update" });
    await user.click(updateButton);

    await waitFor(() => expect(updateButton).toBeDisabled());

    await act(async () => {
      resolveUpdate({ ok: true });
      await updatePromise;
    });

    await waitFor(() => expect(updateButton).toBeEnabled());
  });
});
