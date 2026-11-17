import Delaunay from "delaunay-find";
import {
  makeCreateContainerFunction,
  Selection,
  VictoryContainer,
  VictoryVoronoiContainer,
  VictoryZoomContainer,
  VoronoiHelpers,
} from "victory";

// Each rendered set of series owns one index. Zoom and resize can change screen
// coordinates without changing the series, so also check both scales on lookup.
export function createTooltipLookup() {
  let geometry;
  let data;
  let mesh;
  return (props, position) => {
    const { x, y } = props.scale;
    const nextGeometry = [...x.domain(), ...x.range(), ...y.domain(), ...y.range()].map(Number).join(",");
    if (geometry !== nextGeometry) {
      data = VoronoiHelpers.getDatasets(props);
      mesh = Delaunay.from(data, (d) => x(d._voronoiX), (d) => y(d._voronoiY));
      geometry = nextGeometry;
    }
    if (!data.length) return [];
    const nearest = mesh.find(position.x, position.y);
    return VoronoiHelpers.findPoints(data, data[nearest]);
  };
}

// Match Victory's leading-only 32 ms throttle. The handler belongs to one chart
// and survives Victory re-creating its event wrappers during pointer updates.
export function createTooltipMoveHandler() {
  const lookup = createTooltipLookup();
  let lastMove = -Infinity;
  return (event, props) => {
    const now = performance.now();
    if (now - lastMove < 32) return [];
    lastMove = now;
    return moveTooltip(event, props, lookup);
  };
}

function moveTooltip(event, props, lookup) {
  const svg = props.parentSVG || Selection.getParentSVG(event);
  const position = Selection.getSVGEventCoordinates(event, svg);
  const points = VoronoiHelpers.withinBounds(props, position) ? lookup(props, position) : [];
  const previous = props.activePoints || [];
  if (previous.length === points.length && points.every((p, i) => p === previous[i])) return [];

  return [
    ...VoronoiHelpers.getParentMutation(points, position, svg),
    ...previous.flatMap((point) => VoronoiHelpers.getInactiveMutations(props, point)),
    ...points.flatMap((point) => VoronoiHelpers.getActiveMutations(props, point)),
  ];
}

export function ChartTooltipContainer(props) {
  return <VictoryVoronoiContainer {...props} />;
}

ChartTooltipContainer.role = "container";
ChartTooltipContainer.defaultEvents = (props) =>
  VictoryVoronoiContainer.defaultEvents(props).map((event) => {
    if (event.target !== "parent") return event;
    const move = (e, targetProps) => props.moveTooltip(e, {
      activateData: true,
      activateLabels: true,
      ...props,
      ...targetProps,
    });
    return { ...event, eventHandlers: { ...event.eventHandlers, onMouseMove: move, onTouchMove: move } };
  });

export function createZoomTooltipContainer() {
  return makeCreateContainerFunction(
    { zoom: VictoryZoomContainer, voronoi: ChartTooltipContainer }, VictoryContainer
  )("zoom", "voronoi");
}
