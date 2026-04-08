function parseINIString(data) {
  const regex = {
    section: /^\s*\[\s*([^\]]*)\s*\]\s*$/,
    param: /^\s*([^=]+?)\s*=\s*(.*?)\s*$/,
    comment: /^\s*;.*$/,
  };
  const value = {};
  const lines = data.split(/[\r\n]+/);
  let section = null;

  lines.forEach((line) => {
    if (regex.comment.test(line)) {
      return;
    }

    if (regex.param.test(line)) {
      const paramMatch = line.match(regex.param);
      if (section) {
        value[section][paramMatch[1]] = paramMatch[2];
      } else {
        value[paramMatch[1]] = paramMatch[2];
      }
      return;
    }

    if (regex.section.test(line)) {
      const sectionMatch = line.match(regex.section);
      value[sectionMatch[1]] = {};
      section = sectionMatch[1];
      return;
    }

    if (line.length === 0 && section) {
      section = null;
    }
  });

  return value;
}

export function getConfig(setCallback) {
  fetch("/api/config/shared")
    .then((response) => {
      if (response.ok) {
        return response.text();
      }
      throw new Error("Something went wrong");
    })
    .then((config) => {
      setCallback(parseINIString(config));
    })
    .catch((_error) => {});
}

export function getRelabelMap(setCallback, experiment = "current") {
  fetch(`/api/experiments/${experiment}/unit_labels`)
    .then((response) => response.json())
    .then((data) => {
      setCallback(data);
    });
}
