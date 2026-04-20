import React from "react";

import ExperimentProfileEditorPage, { ExperimentProfileEditorContent } from "./ExperimentProfileEditor";

export function EditExperimentProfilesContent({ initialCode, profileFilename }) {
  return (
    <ExperimentProfileEditorContent
      initialCode={initialCode}
      initialFilename={profileFilename}
      filenameEditable={false}
      onSave={async () => {}}
    />
  );
}

export default function EditExperimentProfile({ title }) {
  return <ExperimentProfileEditorPage mode="edit" title={title} />;
}
