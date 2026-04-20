import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { MemoryRouter } = require("react-router");
const { ExperimentProfileEditorContent, formatProfileSaveError } = require("../ExperimentProfileEditor");

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
      initialCode: "experiment_profile_name: draft\npioreactors:\n  xr1:\n    jobs: {}\n",
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
      initialCode: `experiment_profile_name:

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
      initialCode: `experiment_profile_name: preview

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
      initialCode: `experiment_profile_name: preview
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
      initialCode: `experiment_profile_name: preview

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
});
