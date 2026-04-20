import React from "react";

import ExperimentProfileEditorPage from "./ExperimentProfileEditor";

export default function CreateExperimentProfile({ title }) {
  return <ExperimentProfileEditorPage mode="create" title={title} />;
}
