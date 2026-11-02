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

// Keep hue and ordering stable; pale entries are darkened for thin lines on white.
const colors = [
  "#0077BB",
  "#009988",
  "#CC3311",
  "#1197CA",
  "#BE5F29",
  "#EE3377",
  "#8E958F",
  "#3F95C3",
  "#33A02C",
  "#C97B7A",
  "#D17703",
  "#A67EBB",
  "#6A3D9A",
  "#739925",
  "#1A9E91",
  "#737B94",
  "#AA5CAA",
  "#15742A",
  "#236AD3",
  "#445210",
  "#0CA330",
  "#311535",
  "#803958",
  "#2CA319",
  "#1734B8",
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
