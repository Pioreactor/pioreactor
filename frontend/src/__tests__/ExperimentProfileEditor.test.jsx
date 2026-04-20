import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { ExperimentProfileEditorContent } = require("../ExperimentProfileEditor");

function getEditorTextarea() {
  const textarea = document.querySelector(".npm__react-simple-code-editor__textarea");

  if (!textarea) {
    throw new Error("Editor textarea not found");
  }

  return textarea;
}

describe("ExperimentProfileEditorContent", () => {
  test("allows editing the filename in create mode", () => {
    render(
      <ExperimentProfileEditorContent
        initialCode={"name: first\n"}
        initialFilename="draft_profile"
        filenameEditable={true}
        onSave={async () => {}}
      />,
    );

    const filenameInput = screen.getByDisplayValue("draft_profile");

    fireEvent.change(filenameInput, {
      target: { value: "new profile.yaml" },
    });

    expect(filenameInput).toHaveValue("new_profile_yaml");
  });

  test("keeps the filename fixed in edit mode", () => {
    render(
      <ExperimentProfileEditorContent
        initialCode={"name: first\n"}
        initialFilename="profile-a.yaml"
        filenameEditable={false}
        onSave={async () => {}}
      />,
    );

    expect(screen.getByLabelText("Filename")).toBeDisabled();
    expect(getEditorTextarea()).toHaveValue("name: first\n");
  });
});
