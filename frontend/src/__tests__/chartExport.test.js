import { cloneChartSvg } from "../utils/chartExport";

test("SVG downloads keep their computed paint and background outside the app", () => {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const label = document.createElementNS(svg.namespaceURI, "text");
  label.textContent = "Temperature";
  label.style.fill = "var(--chart-text)";
  svg.appendChild(label);
  const computedStyle = jest.spyOn(window, "getComputedStyle").mockImplementation(() => ({
    getPropertyValue: (property) => ({ fill: "rgb(241, 240, 245)", stroke: "none", color: "rgb(241, 240, 245)" })[property],
  }));
  try {
    const clone = cloneChartSvg(svg, "#22232b");
    expect(clone.querySelector("text").style.fill).toBe("rgb(241, 240, 245)");
    expect(clone.firstChild.tagName).toBe("rect");
    expect(clone.firstChild.getAttribute("fill")).toBe("#22232b");
    expect(new XMLSerializer().serializeToString(clone)).not.toContain("var(");
    expect(svg.querySelector("rect")).toBeNull();
    expect(label.style.fill).toBe("var(--chart-text)");
  } finally {
    computedStyle.mockRestore();
  }
});
