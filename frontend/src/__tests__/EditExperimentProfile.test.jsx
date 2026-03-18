import React from "react";
import { fireEvent, render } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { EditExperimentProfilesContent } = require("../EditExperimentProfile");

function getEditorTextarea() {
  const textarea = document.querySelector(".npm__react-simple-code-editor__textarea");

  if (!textarea) {
    throw new Error("Editor textarea not found");
  }

  return textarea;
}

describe("EditExperimentProfilesContent", () => {
  test("keeps in-progress edits when initialCode changes for the same profile identity", () => {
    const { rerender } = render(
      <EditExperimentProfilesContent
        initialCode={"name: first\n"}
        profileFilename="profile-a.yaml"
      />,
    );

    fireEvent.input(getEditorTextarea(), {
      target: { value: "name: edited\n" },
    });

    rerender(
      <EditExperimentProfilesContent
        initialCode={"name: server update\n"}
        profileFilename="profile-a.yaml"
      />,
    );

    expect(getEditorTextarea()).toHaveValue("name: edited\n");
  });

  test("resets editor state when the profile identity changes", () => {
    const { rerender } = render(
      <EditExperimentProfilesContent
        key="profile-a.yaml"
        initialCode={"name: first\n"}
        profileFilename="profile-a.yaml"
      />,
    );

    fireEvent.input(getEditorTextarea(), {
      target: { value: "name: edited\n" },
    });

    rerender(
      <EditExperimentProfilesContent
        key="profile-b.yaml"
        initialCode={"name: second\n"}
        profileFilename="profile-b.yaml"
      />,
    );

    expect(getEditorTextarea()).toHaveValue("name: second\n");
  });
});
