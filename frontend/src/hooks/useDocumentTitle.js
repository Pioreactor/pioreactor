import { useEffect } from "react";
import { useExperiment } from "../providers/ExperimentContext";

export default function useDocumentTitle(title) {
  const { experimentMetadata } = useExperiment() || {};
  const experiment = experimentMetadata?.experiment;

  useEffect(() => {
    document.title = experiment ? `${title} ~ ${experiment}` : title;
  }, [title, experiment]);
}
