import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../providers/MQTTContext", () => ({
  MQTTProvider: ({ children }) => <>{children}</>,
  useMQTT: () => ({
    client: null,
    subscribeToTopic: jest.fn(),
    unsubscribeFromTopic: jest.fn(),
  }),
}));

jest.mock("material-ui-confirm", () => ({
  useConfirm: () => jest.fn(() => Promise.resolve()),
}));

const { DirectoryNavigatorCard, LeaderCard, LeaderJobs } = require("../Leader");

describe("LeaderCard", () => {
  beforeEach(() => {
    global.fetch = jest.fn((url) => {
      if (url === "/unit_api/system/ipv4") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ ipv4_address: "192.168.1.5" }),
        });
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
  });

  test("renders leader IPv4 from unit API", async () => {
    render(<LeaderCard leaderHostname="leader" />);

    await screen.findByText("192.168.1.5");
    expect(global.fetch).toHaveBeenCalledWith("/unit_api/system/ipv4");
  });
});

test.each([
  ["monitor", "/unit_api/jobs/stop"],
  ["web server and queue", "/unit_api/system/web_server/restart"],
])("restarting %s targets the configured leader", async (job, endpoint) => {
  global.fetch = jest.fn((url) => Promise.resolve({
    ok: true,
    json: async () => url.endsWith("/running") ? [] : { state: "ready" },
  }));
  render(<LeaderJobs leaderHostname="leader-unit" />);
  fireEvent.click(screen.getByRole("button", { name: `More actions for ${job}` }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Restart" }));
  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(endpoint, expect.objectContaining({
    method: "POST",
    headers: expect.objectContaining({ "X-Pioreactor-Target": "leader-unit" }),
  })));
});

test("archive import carries identity without overriding the multipart content type", async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ dirs: [], files: [] }) });
  const alert = jest.spyOn(window, "alert").mockImplementation(() => {});
  try {
    const { container } = render(<DirectoryNavigatorCard leaderHostname="leader-unit" />);
    const archive = new File(["archive"], "backup.zip", { type: "application/zip" });
    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [archive] } });
    await waitFor(() => expect(alert).toHaveBeenCalled());
    const [, options] = global.fetch.mock.calls.find(([url]) => url === "/unit_api/import_zipped_dot_pioreactor");
    expect(options.headers).toEqual({ "X-Pioreactor-Target": "leader-unit" });
    expect(options.body.get("archive")).toBe(archive);
  } finally {
    alert.mockRestore();
  }
});
