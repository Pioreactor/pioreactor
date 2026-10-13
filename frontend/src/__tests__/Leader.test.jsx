import React from "react";
import { render, screen } from "@testing-library/react";
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

const { LeaderCard } = require("../Leader");

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
