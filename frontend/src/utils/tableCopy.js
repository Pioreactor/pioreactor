function normalizedCellText(cell) {
  const copyValue = cell.getAttribute("data-copy-value");
  if (copyValue !== null) {
    return copyValue;
  }

  return cell.textContent.replace(/\s+/g, " ").trim();
}

function selectionIntersectsNode(ranges, node) {
  return ranges.some((range) => {
    try {
      return range.intersectsNode(node);
    } catch {
      return false;
    }
  });
}

export function copySelectedTableRowsAsTsv(event) {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
    return;
  }

  const table = event.currentTarget.querySelector("table");
  if (!table) {
    return;
  }

  const ranges = Array.from({ length: selection.rangeCount }, (_, index) => selection.getRangeAt(index));
  if (!selectionIntersectsNode(ranges, table)) {
    return;
  }

  const rows = Array.from(table.querySelectorAll("tr"))
    .filter((row) => row.getAttribute("data-copy-row") !== "false")
    .filter((row) => selectionIntersectsNode(ranges, row));

  const copiedText = rows
    .map((row) =>
      Array.from(row.querySelectorAll("th, td"))
        .map(normalizedCellText)
        .join("\t")
    )
    .filter(Boolean)
    .join("\n");

  if (!copiedText) {
    return;
  }

  event.clipboardData.setData("text/plain", copiedText);
  event.preventDefault();
}
