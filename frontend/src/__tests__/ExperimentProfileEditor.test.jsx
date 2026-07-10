import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { MemoryRouter } = require("react-router");
const { ExperimentProfileEditorContent, formatProfileSaveError } = require("../ExperimentProfileEditor");
const CreateExperimentProfile = require("../CreateExperimentProfile").default;

function getEditorTextarea() {
  const textarea = document.querySelector(".npm__react-simple-code-editor__textarea");

  if (!textarea) {
    throw new Error("Editor textarea not found");
  }

  return textarea;
}

function renderEditor(props) {
  return render(
    <MemoryRouter>
      <ExperimentProfileEditorContent {...props} />
    </MemoryRouter>,
  );
}

describe("ExperimentProfileEditorContent", () => {
  test("starts new profiles with an explicit quoted v1 version", () => {
    render(
      <MemoryRouter>
        <CreateExperimentProfile title="Create profile" />
      </MemoryRouter>,
    );

    expect(getEditorTextarea().value).toMatch(/^version: "1\.0"\n/);
  });

  test("returns plain text save errors from the backend", () => {
    expect(formatProfileSaveError("leader returned plain text error")).toBe("leader returned plain text error");
  });

  test("allows editing the filename in create mode", () => {
    renderEditor(
      {
        initialCode: "name: first\n",
        initialFilename: "draft_profile",
        filenameEditable: true,
        onSave: async () => {},
      },
    );

    const filenameInput = screen.getByDisplayValue("draft_profile");

    fireEvent.change(filenameInput, {
      target: { value: "new profile.yaml" },
    });

    expect(filenameInput).toHaveValue("new_profile_yaml");
  });

  test("shows save failures and re-enables the save button", async () => {
    const onSave = jest.fn(() => Promise.reject(new Error("YAML is invalid")));
    renderEditor(
      {
        initialCode: "name: first\n",
        initialFilename: "draft_profile",
        filenameEditable: true,
        onSave,
      },
    );

    fireEvent.change(getEditorTextarea(), {
      target: { value: "name: changed\n" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    expect(screen.getByRole("button", { name: /saving/i })).toBeDisabled();

    await screen.findByText("YAML is invalid");
    await waitFor(() => expect(screen.getByRole("button", { name: /save/i })).not.toBeDisabled());
  });

  test("saves changes and disables the save button after success", async () => {
    const onSave = jest.fn(() => Promise.resolve());
    renderEditor(
      {
        initialCode: "name: first\n",
        initialFilename: "draft_profile",
        filenameEditable: true,
        onSave,
      },
    );

    fireEvent.change(getEditorTextarea(), {
      target: { value: "name: changed\n" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /save/i })).toBeDisabled());
    expect(onSave).toHaveBeenCalledWith({
      code: "name: changed\n",
      filename: "draft_profile",
    });
  });

  test("keeps the filename fixed in edit mode", () => {
    renderEditor(
      {
        initialCode: "name: first\n",
        initialFilename: "profile-a.yaml",
        filenameEditable: false,
        onSave: async () => {},
      },
    );

    expect(screen.getByLabelText("Filename")).toBeDisabled();
    expect(getEditorTextarea()).toHaveValue("name: first\n");
  });

  test("does not crash when the editor is cleared completely", () => {
    renderEditor({
      initialCode: 'version: "1.0"\nexperiment_profile_name: draft\npioreactors:\n  xr1:\n    jobs: {}\n',
      initialFilename: "draft_profile",
      filenameEditable: true,
      onSave: async () => {},
    });

    fireEvent.change(getEditorTextarea(), {
      target: { value: "" },
    });

    expect(screen.getByText("??")).toBeInTheDocument();
  });

  test("does not crash when a log message is temporarily an object", () => {
    renderEditor({
      initialCode: `version: "1.0"
experiment_profile_name:

metadata:
  author:
  description:

pioreactors:
  xr1:
    jobs:
      add_media:
        actions:
          - type: log
            t: 0s
            options:
              message: {}
`,
      initialFilename: "draft_profile",
      filenameEditable: true,
      onSave: async () => {},
    });

    expect(screen.getAllByText("xr1").length).toBeGreaterThan(0);
  });

  test("shows falsy log messages instead of hiding them", () => {
    renderEditor({
      initialCode: `version: "1.0"
experiment_profile_name: preview

pioreactors:
  xr1:
    jobs:
      add_media:
        actions:
          - type: log
            t: 0s
            options:
              message: 0
`,
      initialFilename: "draft_profile",
      filenameEditable: true,
      onSave: async () => {},
    });

    expect(screen.getAllByText("0").length).toBeGreaterThan(1);
  });

  test("shows invalid inputs as malformed instead of rendering an empty section", () => {
    renderEditor({
      initialCode: `version: "1.0"
experiment_profile_name: preview
inputs: hello
`,
      initialFilename: "draft_profile",
      filenameEditable: true,
      onSave: async () => {},
    });

    expect(screen.getByText("inputs??")).toBeInTheDocument();
  });

  test("shows malformed config overrides instead of dropping them", () => {
    renderEditor({
      initialCode: `version: "1.0"
experiment_profile_name: preview

pioreactors:
  xr1:
    jobs:
      stirring:
        actions:
          - type: update
            t: 0s
            config_overrides:
              target_rpm: {}
`,
      initialFilename: "draft_profile",
      filenameEditable: true,
      onSave: async () => {},
    });

    expect(screen.getAllByText("??").length).toBeGreaterThan(0);
  });

  test("shows invalid config overrides syntax when config overrides are written as a list", () => {
    renderEditor({
      initialCode: `version: "1.0"
experiment_profile_name: preview

pioreactors:
  xr1:
    jobs:
      stirring:
        actions:
          - type: update
            t: 0s
            options:
              target_rpm: 500
            config_overrides:
              - target_rpm: 500
`,
      initialFilename: "draft_profile",
      filenameEditable: true,
      onSave: async () => {},
    });

    expect(screen.getByText("invalid config overrides syntax!")).toBeInTheDocument();
  });
});
