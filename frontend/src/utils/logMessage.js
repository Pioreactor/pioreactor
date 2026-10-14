// Log messages mark entity names with backticks, e.g. "Saved calibration `od-cal-1`".
// The raw message stays plain text; this module only decides how to present it.

const KEYWORD_ENTITY_TYPES = {
  experiment: "experiment",
  calibration: "calibration",
  estimator: "estimator",
  pioreactor: "pioreactor",
  worker: "pioreactor",
  unit: "pioreactor",
};

// Matches the word directly before an opening backtick, allowing a plural such as "workers" or "Worker(s)".
const PRECEDING_KEYWORD_REGEX = /([A-Za-z]+?)(?:s|\(s\))?\s+$/;

function precedingKeywordType(precedingText) {
  const match = precedingText.match(PRECEDING_KEYWORD_REGEX);
  if (!match) {
    return null;
  }
  return KEYWORD_ENTITY_TYPES[match[1].toLowerCase()] ?? null;
}

function classifySpan(text, precedingText, { units, experiment }) {
  const keywordType = precedingKeywordType(precedingText);
  if (keywordType) {
    return keywordType;
  }
  if (units?.has(text)) {
    return "pioreactor";
  }
  if (experiment && experiment === text) {
    return "experiment";
  }
  return "code";
}

// Splits a message into text and entity segments. A message with unbalanced backticks
// (such as an exception or SQL fragment) is returned as one text segment.
export function parseLogMessage(message, context = {}) {
  const parts = String(message).split("`");
  if (parts.length < 3 || parts.length % 2 === 0) {
    return [{ type: "text", text: String(message) }];
  }

  const segments = [];
  parts.forEach((part, index) => {
    if (index % 2 === 0) {
      if (part) {
        segments.push({ type: "text", text: part });
      }
    } else if (part === "") {
      segments.push({ type: "text", text: "``" });
    } else {
      segments.push({ type: classifySpan(part, parts[index - 1], context), text: part });
    }
  });
  return segments;
}
