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
  "#803958",
  "#1734B8",
  "#15742A",
  "#EE3377",
  "#3F95C3",
  "#0CA330",
  "#6A3D9A",
  "#236AD3",
  "#C97B7A",
  "#AA5CAA",
  "#737B94",
  "#8E958F",
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
