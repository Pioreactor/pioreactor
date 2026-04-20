import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { MemoryRouter, Route, Routes, useLocation } = require("react-router");

const mockStartProfile = jest.fn();

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: () => ({
    experimentMetadata: { experiment: "exp-1" },
    allExperiments: [{ experiment: "exp-1", description: "", tags: [] }],
    updateExperiment: jest.fn(),
    setAllExperiments: jest.fn(),
  }),
}));

jest.mock("../providers/RunningProfilesContext", () => ({
  RunningProfilesProvider: ({ children }) => <>{children}</>,
  useRunningProfiles: () => ({
    runningProfiles: [],
    loading: false,
    stopProfile: jest.fn(),
    startProfile: mockStartProfile,
  }),
}));

jest.mock("material-ui-confirm", () => ({
  useConfirm: () => jest.fn(() => Promise.resolve()),
}));

jest.mock("../components/ManageExperimentMenu", () => () => <div data-testid="manage-experiment-menu" />);
jest.mock("../components/SelectButton", () => ({ onClick, disabled }) => (
  <button onClick={onClick} disabled={disabled} type="button">
    Run profile
  </button>
));
jest.mock("../components/DisplaySourceCode", () => ({ sourceCode }) => <pre>{sourceCode}</pre>);
jest.mock("../components/DisplayProfile", () => ({
  DisplayProfile: ({ data }) => <div>Preview: {data.experiment_profile_name}</div>,
}));

const { Profiles } = require("../Profiles");

const profileSources = {
  "profile-a.yaml": `experiment_profile_name: Profile A
metadata:
  author: Alice
`,
  "profile-b.yaml": `experiment_profile_name: Profile B
metadata:
  author: Bob
`,
};

const profilesResponse = [
  {
    file: "profile-a.yaml",
    fullpath: "/tmp/profile-a.yaml",
    experimentProfile: { experiment_profile_name: "Profile A" },
  },
  {
    file: "profile-b.yaml",
    fullpath: "/tmp/profile-b.yaml",
    experimentProfile: { experiment_profile_name: "Profile B" },
  },
];

function NewProfileLocationState() {
  const location = useLocation();
  return <pre data-testid="new-profile-state">{JSON.stringify(location.state)}</pre>;
}

function renderProfiles(initialEntry = "/experiment-profiles/profile-a.yaml") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/experiment-profiles/new" element={<NewProfileLocationState />} />
        <Route path="/experiment-profiles/:profileFilename" element={<Profiles title="Profiles" />} />
      </Routes>
    </MemoryRouter>,
  );
}

function countFetches(url) {
  return global.fetch.mock.calls.filter(([calledUrl]) => calledUrl === url).length;
}

describe("Profiles", () => {
  beforeEach(() => {
    mockStartProfile.mockReset();
    global.fetch = jest.fn((url) => {
      if (url === "/api/experiment_profiles") {
        return Promise.resolve({
          ok: true,
          json: async () => profilesResponse,
        });
      }

      if (url === "/api/experiments/exp-1/experiment_profiles/recent") {
        return Promise.resolve({
          ok: true,
          json: async () => [],
        });
      }

      if (url === "/api/experiments/exp-1/experiment_profiles/running") {
        return Promise.resolve({
          ok: true,
          json: async () => [],
        });
      }

      if (url in {
        "/api/experiment_profiles/profile-a.yaml": true,
        "/api/experiment_profiles/profile-b.yaml": true,
      }) {
        const filename = url.split("/").pop();
        return Promise.resolve({
          ok: true,
          text: async () => profileSources[filename],
        });
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
  });

  test("reuses the loaded profile source for view source and duplicate", async () => {
    renderProfiles();

    await screen.findByText("Preview: Profile A");
    await waitFor(() => expect(countFetches("/api/experiment_profiles/profile-a.yaml")).toBe(1));

    fireEvent.click(screen.getByRole("button", { name: /view source/i }));

    await screen.findByText(/experiment_profile_name: Profile A/);
    expect(countFetches("/api/experiment_profiles/profile-a.yaml")).toBe(1);

    fireEvent.click(screen.getByRole("button", { name: /duplicate/i }));

    const duplicatedState = JSON.parse((await screen.findByTestId("new-profile-state")).textContent);
    expect(duplicatedState).toEqual({
      initialCode: profileSources["profile-a.yaml"],
      initialFilename: "profile-a_copy",
    });
    expect(countFetches("/api/experiment_profiles/profile-a.yaml")).toBe(1);
  });

  test("changes selection through the route without refetching the profile list", async () => {
    renderProfiles();

    await screen.findByText("Preview: Profile A");
    await waitFor(() => expect(countFetches("/api/experiment_profiles")).toBe(1));

    fireEvent.mouseDown(screen.getByRole("combobox"));
    fireEvent.click(await screen.findByRole("option", { name: "Profile B" }));

    await screen.findByText("Preview: Profile B");
    await waitFor(() => expect(countFetches("/api/experiment_profiles/profile-b.yaml")).toBe(1));

    expect(countFetches("/api/experiment_profiles")).toBe(1);
    expect(countFetches("/api/experiment_profiles/profile-a.yaml")).toBe(1);
  });
});
