// Compare two config.ini texts by section and key, the way ConfigParser reads
// them (strict=False, case-preserving keys), ignoring comments and formatting.

const SECTION_RE = /^\s*\[([^\]]+)\]/;


export function parseIni(text) {
  const sections = new Map();
  let current = null;
  let lastKey = null;

  for (const line of (text || "").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (trimmed === "" || trimmed.startsWith("#") || trimmed.startsWith(";")) {
      lastKey = null;
      continue;
    }

    const sectionMatch = line.match(SECTION_RE);
    if (sectionMatch) {
      const name = sectionMatch[1].trim();
      if (!sections.has(name)) {
        sections.set(name, new Map());
      }
      current = sections.get(name);
      lastKey = null;
      continue;
    }

    if (current === null) {
      continue;
    }

    // Indented lines continue the previous value.
    if (/^\s/.test(line) && lastKey !== null) {
      const previous = current.get(lastKey);
      current.set(lastKey, previous === null ? trimmed : `${previous}\n${trimmed}`);
      continue;
    }

    const delimiterIndex = line.search(/[=:]/);
    if (delimiterIndex === -1) {
      current.set(trimmed, null);
      lastKey = trimmed;
      continue;
    }

    const key = line.slice(0, delimiterIndex).trim();
    current.set(key, line.slice(delimiterIndex + 1).trim());
    lastKey = key;
  }

  return sections;
}


// Keep removed names near where they used to be, so the summary reads in file order.
function mergeOrder(oldNames, newNames) {
  const newSet = new Set(newNames);
  const merged = [...newNames];
  oldNames.forEach((name, index) => {
    if (newSet.has(name)) {
      return;
    }
    const anchor = oldNames.slice(0, index).reverse().find((previous) => merged.includes(previous));
    merged.splice(anchor === undefined ? 0 : merged.indexOf(anchor) + 1, 0, name);
  });
  return merged;
}


export function diffConfigs(oldText, newText) {
  const oldSections = parseIni(oldText);
  const newSections = parseIni(newText);
  const sectionNames = mergeOrder([...oldSections.keys()], [...newSections.keys()]);
  const changes = [];

  for (const name of sectionNames) {
    const oldEntries = oldSections.get(name);
    const newEntries = newSections.get(name);
    const sectionStatus = !oldEntries ? "added" : !newEntries ? "removed" : "changed";
    const before = oldEntries || new Map();
    const after = newEntries || new Map();
    const entries = [];

    for (const key of mergeOrder([...before.keys()], [...after.keys()])) {
      if (!before.has(key)) {
        entries.push({ key, status: "added", newValue: after.get(key) });
      } else if (!after.has(key)) {
        entries.push({ key, status: "removed", oldValue: before.get(key) });
      } else if (before.get(key) !== after.get(key)) {
        entries.push({ key, status: "changed", oldValue: before.get(key), newValue: after.get(key) });
      }
    }

    if (sectionStatus !== "changed" || entries.length > 0) {
      changes.push({ name, status: sectionStatus, entries });
    }
  }

  return changes;
}
