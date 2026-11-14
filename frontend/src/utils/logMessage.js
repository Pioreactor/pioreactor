// Log messages mark entity names with backticks, e.g. "Saved calibration `od-cal-1`".
// The raw message stays plain text; this module only decides how to present it.

const KEYWORD_ENTITY_TYPES = {
  experiment: "experiment",
  calibration: "calibration",
  estimator: "estimator",
  plugin: "plugin",
  pioreactor: "pioreactor",
  worker: "pioreactor",
  unit: "pioreactor",
  leader: "pioreactor",
};

// Matches the word directly before an opening backtick, allowing a plural such as "workers" or "Worker(s)".
const PRECEDING_KEYWORD_REGEX = /([A-Za-z]+?)(?:s|\(s\))?\s+$/;

// Only exact device keys qualify: prose such as "Saved calibration" is not a device.
const CALIBRATION_DEVICE_REGEX = /\b(stirring|media_pump|alt_media_pump|waste_pump|od(?:45|90|135|180)?)\s+calibration\s+$/;

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
      const type = classifySpan(part, parts[index - 1], context);
      const segment = { type, text: part };
      if (type === "calibration") {
        const deviceMatch = parts[index - 1].match(CALIBRATION_DEVICE_REGEX);
        if (deviceMatch) {
          segment.device = deviceMatch[1];
        }
      }
      segments.push(segment);
    }
  });
  return segments;
}

const TRACEBACK_HEADER = "Traceback (most recent call last):";
// Python 3.11+ underlines the failing expression with lines made only of ~ and ^.
const TRACEBACK_MARKER_LINE = /^\s*[~^]+\s*$/;
const SITE_PACKAGES_PREFIX = /File "[^"]*\/site-packages\//g;

// Splits a message with an appended traceback (from `exc_info`) into the logged summary,
// the final exception line, and a tidied traceback for display. Messages without a traceback
// come back unchanged as the summary.
export function splitTraceback(message) {
  const text = String(message);
  const tracebackStart = text.indexOf(TRACEBACK_HEADER);
  if (tracebackStart === -1) {
    return { summary: text, exceptionLine: null, traceback: null };
  }

  const summary = text.slice(0, tracebackStart).trimEnd();
  const tracebackLines = text.slice(tracebackStart).trimEnd().split("\n");
  const exceptionLine = [...tracebackLines]
    .reverse()
    .find((line) => line.trim() && !/^\s/.test(line) && line !== TRACEBACK_HEADER) ?? null;

  // The summary is often the exception message itself, e.g. logger.error(str(e), exc_info=True).
  const exceptionMessage = exceptionLine?.slice(exceptionLine.indexOf(":") + 1).trim();
  const summaryRepeatsException = Boolean(summary && exceptionMessage && summary.includes(exceptionMessage));

  return {
    summary,
    exceptionLine: summaryRepeatsException ? null : exceptionLine,
    traceback: tracebackLines
      .filter((line) => !TRACEBACK_MARKER_LINE.test(line))
      .join("\n")
      .replace(SITE_PACKAGES_PREFIX, 'File "'),
  };
}
