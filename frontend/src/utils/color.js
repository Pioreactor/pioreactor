import { uiColors } from "../theme/colors";
class ColorCycler {
  constructor(colors) {
    this.colors = colors;
    this.index = 0;
    this.data = {};
    return new Proxy(this, {
      get: (target, property) => {
        if (property in target.data) {
          return target.data[property];
        }
        const color = target.colors[target.index];
        target.index = (target.index + 1) % target.colors.length;
        target.data[property] = color;
        return color;
      },
    });
  }
}

// Units take colors in order, so the first slots are the most distinct, including under
// red-green colour blindness. Keep slots 0-2 fixed; near-duplicates sit at the end.
const colors = [
  "#0077BB",
  "#009988",
  "#CC3311",
  "#D17703",
  "#904867",
  "#254ACE",
  "#268036",
  "#EE3377",
  "#A670F3",
  "#7C92BE",
  "#6A3D9A",
  "#58502F",
  "#950681",
  "#C18473",
  "#829821",
  "#2B5957",
  "#A67EBB",
  "#1197CA",
  "#739925",
  "#BE5F29",
  "#2CA319",
  "#445210",
  "#33A02C",
  "#1A9E91",
  "#311535",
];

// Colors offered when choosing a unit's Overview line color: the distinct slots, not the near-duplicates.
const unitColorChoices = colors.slice(0, 16);

// Chosen colors win. Other units keep their usual slot (sorted unit N gets colors[N-1]) unless a chosen
// color took it; those units, and units first seen later (e.g. only in chart history), take the first
// unused color.
function createUnitColorMap(units, chosenColors = {}) {
  const resolved = { ...chosenColors };
  const used = new Set(Object.values(chosenColors));
  const nextUnusedColor = () => {
    const color = colors.find((candidate) => !used.has(candidate)) ?? colors[used.size % colors.length];
    used.add(color);
    return color;
  };
  const displaced = [];
  units.forEach((unit, index) => {
    if (unit in resolved) {
      return;
    }
    const usualColor = colors[index % colors.length];
    if (used.has(usualColor)) {
      displaced.push(unit);
    } else {
      resolved[unit] = usualColor;
      used.add(usualColor);
    }
  });
  displaced.forEach((unit) => {
    resolved[unit] = nextUnusedColor();
  });
  return new Proxy(resolved, {
    get: (target, property) => {
      if (typeof property === "string" && !(property in target)) {
        target[property] = nextUnusedColor();
      }
      return target[property];
    },
  });
}

const ERROR_COLOR = uiColors.logError;
const WARNING_COLOR = uiColors.logWarning;
const NOTICE_COLOR = uiColors.logNotice;

const readyGreen = uiColors.ready;
const disconnectedGrey = uiColors.disconnected;
const lostRed = uiColors.lost;
const defaultStateDisplayBackground = uiColors.stateBackground;
const disabledColor = uiColors.disabled;
const inactiveGrey = uiColors.inactive;

const stateDisplay = {
  init: { display: "Starting", color: readyGreen, backgroundColor: uiColors.readyBackground },
  ready: { display: "On", color: readyGreen, backgroundColor: uiColors.readyBackground },
  sleeping: { display: "Paused", color: disconnectedGrey, backgroundColor: defaultStateDisplayBackground },
  disconnected: { display: "Off", color: disconnectedGrey, backgroundColor: defaultStateDisplayBackground },
  lost: { display: "Lost", color: lostRed, backgroundColor: defaultStateDisplayBackground },
  NA: { display: "Not available", color: disconnectedGrey, backgroundColor: defaultStateDisplayBackground },
};

export {
  ColorCycler,
  colors,
  createUnitColorMap,
  unitColorChoices,
  ERROR_COLOR,
  WARNING_COLOR,
  NOTICE_COLOR,
  readyGreen,
  disconnectedGrey,
  lostRed,
  defaultStateDisplayBackground,
  disabledColor,
  inactiveGrey,
  stateDisplay,
};
