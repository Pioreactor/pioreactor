import yaml from "js-yaml";

function addQuotesToBrackets(input) {
  return input.replace(/(\${0}){{(.*?)}}/g, (match, _p1, p2, offset, string) => {
    if (string[offset - 1] !== "$") {
      return `"{{${p2}}}"`;
    }
    return match;
  });
}

function findInlineCommentStart(line) {
  let inSingleQuote = false;
  let inDoubleQuote = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    const previous = line[i - 1];

    if (char === "'" && !inDoubleQuote) {
      inSingleQuote = !inSingleQuote;
      continue;
    }

    if (char === '"' && !inSingleQuote && previous !== "\\") {
      inDoubleQuote = !inDoubleQuote;
      continue;
    }

    if (char === "#" && !inSingleQuote && !inDoubleQuote) {
      return i;
    }
  }

  return -1;
}

function splitYamlLineAndComment(line) {
  const commentStart = findInlineCommentStart(line);
  if (commentStart === -1) {
    return { yamlPart: line, comment: null };
  }

  return {
    yamlPart: line.slice(0, commentStart),
    comment: line.slice(commentStart + 1).trim(),
  };
}

function pathJoin(basePath, nextPart) {
  if (!basePath) {
    return nextPart;
  }

  if (nextPart.startsWith("[")) {
    return `${basePath}${nextPart}`;
  }

  return `${basePath}.${nextPart}`;
}

function extractInlineComments(yamlString) {
  const comments = {};
  const lines = yamlString.split(/\r?\n/);
  const stack = [{ indent: -1, path: "" }];
  const sequenceIndices = new Map();

  const pushContext = (indent, path) => {
    stack.push({ indent, path });
  };

  const recordComment = (path, comment) => {
    if (path && comment) {
      comments[path] = comment;
    }
  };

  for (const rawLine of lines) {
    if (!rawLine.trim() || rawLine.trimStart().startsWith("#")) {
      continue;
    }

    const indent = rawLine.length - rawLine.trimStart().length;
    const { yamlPart, comment } = splitYamlLineAndComment(rawLine);
    const content = yamlPart.trim();

    if (!content) {
      continue;
    }

    while (stack.length > 1 && indent <= stack[stack.length - 1].indent) {
      stack.pop();
    }

    const parentPath = stack[stack.length - 1].path;

    if (content.startsWith("- ")) {
      const sequencePath = parentPath;
      const currentIndex = sequenceIndices.get(sequencePath) ?? 0;
      sequenceIndices.set(sequencePath, currentIndex + 1);

      const itemPath = pathJoin(sequencePath, `[${currentIndex}]`);
      pushContext(indent, itemPath);

      const remainder = content.slice(2).trim();
      if (!remainder) {
        recordComment(itemPath, comment);
        continue;
      }

      const separatorIndex = remainder.indexOf(":");
      if (separatorIndex === -1) {
        recordComment(itemPath, comment);
        continue;
      }

      const key = remainder.slice(0, separatorIndex).trim();
      const rawValue = remainder.slice(separatorIndex + 1).trim();
      const entryPath = pathJoin(itemPath, key);
      recordComment(entryPath, comment);

      if (!rawValue) {
        pushContext(indent + 1, entryPath);
      }
      continue;
    }

    const separatorIndex = content.indexOf(":");
    if (separatorIndex === -1) {
      continue;
    }

    const key = content.slice(0, separatorIndex).trim();
    const rawValue = content.slice(separatorIndex + 1).trim();
    const entryPath = pathJoin(parentPath, key);
    recordComment(entryPath, comment);

    if (!rawValue) {
      pushContext(indent, entryPath);
    }
  }

  return comments;
}

export function convertYamlToProfilePreview(yamlString) {
  try {
    return {
      data: yaml.load(addQuotesToBrackets(yamlString)),
      comments: extractInlineComments(yamlString),
    };
  } catch (error) {
    return { error: error.message, comments: {} };
  }
}

export function getInlineCommentForPath(comments, path) {
  if (!comments || !path) {
    return null;
  }

  return comments[path] ?? null;
}
