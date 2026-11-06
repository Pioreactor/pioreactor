import React from "react";
import { act, render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({ client: null, subscribeToTopic: jest.fn(), unsubscribeFromTopic: jest.fn() }),
}));
jest.mock("../components/LogMessage", () => ({
  __esModule: true,
  default: () => null,
  useClusterUnits: () => new Set(),
}));
jest.mock("material-ui-confirm", () => ({ useConfirm: () => jest.fn() }));

const { MemoryRouter } = require("react-router");
const MediaCard = require("../components/MediaCard").default;
const LogTable = require("../components/LogTable").default;
const { RunningProfilesContainer } = require("../Profiles");
const { RunningProfilesProvider } = require("../providers/RunningProfilesContext");

const cards = [
  {
    name: "Dosing",
    element: <MediaCard experiment="exp1" startedAt="2026-11-06T12:00:00Z" />,
    empty: "No Pioreactors have been assigned to this experiment.",
    loading: "Loading dosing data",
  },
  {
    name: "Recent experiment logs",
    element: <LogTable units={[]} experiment="exp1" config={{ logging: { ui_log_level: "info" } }} />,
    empty: /No recent experiment logs/,
    loading: "Loading recent experiment logs",
  },
  {
    name: "Profiles running",
    element: <RunningProfilesProvider experiment="exp1"><RunningProfilesContainer /></RunningProfilesProvider>,
    empty: "No profiles are currently running.",
    loading: "Loading running profiles",
  },
];

function emptyResponse(url) {
  return {
    ok: true,
    json: async () => url.includes("/media_rates?")
      ? { all: { mediaRate: 0, altMediaRate: 0 } }
      : [],
  };
}

test.each(cards)("$name shows a spinner until an empty response succeeds", async ({ element, loading, empty }) => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  global.fetch = jest.fn(url => pending.then(() => emptyResponse(url)));
  render(<MemoryRouter>{element}</MemoryRouter>);

  expect(screen.getByRole("progressbar", { name: loading })).toBeInTheDocument();
  expect(screen.queryByText(empty)).not.toBeInTheDocument();
  await act(async () => finish());

  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  expect(screen.getByText(empty)).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test.each(cards)("$name reports failed requests instead of an empty result", async ({ element, empty }) => {
  global.fetch = jest.fn(async () => ({ ok: false, status: 500 }));
  render(<MemoryRouter>{element}</MemoryRouter>);

  expect(await screen.findByRole("alert")).toHaveTextContent("Refresh the page to try again.");
  expect(screen.queryByText(empty)).not.toBeInTheDocument();
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
});

test("Dosing waits for media rates and reports a network failure", async () => {
  let failRates;
  global.fetch = jest.fn(url => url.includes("/media_rates?")
    ? new Promise((_resolve, reject) => { failRates = reject; })
    : Promise.resolve(emptyResponse(url)));
  render(<MemoryRouter>{cards[0].element}</MemoryRouter>);
  await act(async () => {});
  expect(screen.getByRole("progressbar", { name: "Loading dosing data" })).toBeInTheDocument();

  await act(async () => failRates(new Error("Network disconnected")));
  expect(screen.getByRole("alert")).toHaveTextContent("Unable to load dosing rates.");
  expect(screen.queryByText(cards[0].empty)).not.toBeInTheDocument();
});

test("a late profiles failure cannot replace the new experiment's result", async () => {
  let finishOldRequest;
  global.fetch = jest.fn(url => url.includes("/exp1/")
    ? new Promise(resolve => { finishOldRequest = resolve; })
    : Promise.resolve(emptyResponse(url)));
  const view = experiment => (
    <MemoryRouter>
      <RunningProfilesProvider experiment={experiment}><RunningProfilesContainer /></RunningProfilesProvider>
    </MemoryRouter>
  );
  const { rerender } = render(view("exp1"));
  rerender(view("exp2"));
  await screen.findByText(cards[2].empty);

  await act(async () => finishOldRequest({ ok: false, status: 500 }));
  expect(screen.getByText(cards[2].empty)).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
