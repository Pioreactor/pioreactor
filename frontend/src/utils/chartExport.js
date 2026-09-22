// Exported SVGs must carry their colours and canvas without the app's CSS.
export function cloneChartSvg(svgElement, background) {
  const clone = svgElement.cloneNode(true);
  const sourceNodes = [svgElement, ...svgElement.querySelectorAll("*")];
  const clonedNodes = [clone, ...clone.querySelectorAll("*")];
  sourceNodes.forEach((node, index) => {
    const style = window.getComputedStyle(node);
    for (const property of ["fill", "stroke", "color"]) {
      clonedNodes[index].style.setProperty(property, style.getPropertyValue(property));
    }
  });

  const canvas = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  canvas.setAttribute("width", "100%");
  canvas.setAttribute("height", "100%");
  canvas.setAttribute("fill", background);
  clone.insertBefore(canvas, clone.firstChild);
  return clone;
}
