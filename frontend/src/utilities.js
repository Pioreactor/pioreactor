
function parseINIString(data){
    var regex = {
        section: /^\s*\[\s*([^\]]*)\s*\]\s*$/,
        param: /^\s*([^=]+?)\s*=\s*(.*?)\s*$/,
        comment: /^\s*;.*$/
    };
    var value = {};
    var lines = data.split(/[\r\n]+/);
    var section = null;
    lines.forEach(function(line){
        if(regex.comment.test(line)){
            return;
        }else if(regex.param.test(line)){
            var match = line.match(regex.param);
            if(section){
                value[section][match[1]] = match[2];
            }else{
                value[match[1]] = match[2];
            }
        }else if(regex.section.test(line)){
            var match = line.match(regex.section);
            value[match[1]] = {};
            section = match[1];
        }else if(line.length === 0 && section){
            section = null;
        };
    });
    return value;
}


export function getConfig(setCallback) {
  fetch("/api/configs/config.ini")
    .then((response) => {
        if (response.ok) {
          return response.text();
        } else {
          throw new Error('Something went wrong');
        }
      })
    .then((config) => {
      setCallback(parseINIString(config));
    })
    .catch((error) => {})
}

export function getRelabelMap(setCallback, experiment="current") {
  fetch(`/api/experiments/${experiment}/unit_labels`)
      .then((response) => {
        return response.json();
      })
      .then((data) => {
        setCallback(data)
  });
}



export function runPioreactorJob(unit, experiment, job, args = [], options = {}, configOverrides={}) {
    return fetch(`/api/workers/${unit}/jobs/run/job_name/${job}/experiments/${experiment}`, {
      method: "PATCH",
      body: JSON.stringify({
        args: args,
        options: options,
        env: {EXPERIMENT: experiment, JOB_SOURCE: "user"},
        config_overrides: Object.entries(configOverrides).map( ( [parameter, value] ) => [`${job}.config`, parameter, value]),
      }),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
    }).then(response => {
      if (response.ok) {
        // If response status is in the range 200-299
        return
      } else {
        throw new Error(`Error ${response.status}.`);
      }
    }).catch(error => {
      // Handle network errors or 4xx/5xx errors
      throw error;
    });
}

export function runPioreactorJobViaUnitAPI(job, args = [], options = {}) {
    return fetch(`/unit_api/jobs/run/job_name/${job}`, {
      method: "PATCH",
      body: JSON.stringify({ args: args, options: options}),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
    }).then(response => {
      if (response.ok) {
        // If response status is in the range 200-299
        return
      } else {
        throw new Error(`Error ${response.status}.`);
      }
    }).catch(error => {
      // Handle network errors or 4xx/5xx errors
      throw error;
    });
}


export class ColorCycler {
  constructor(colors) {
    this.colors = colors;
    this.index = 0;
    this.data = {};
    return new Proxy(this, {
      get: (target, property) => {
        if (property in target.data) {
          return target.data[property];
        } else {
          const color = target.colors[target.index];
          target.index = (target.index + 1) % target.colors.length;
          target.data[property] = color;
          return color;
        }
      }
    });
  }
}


export const colors = [
  "#0077BB",
  "#009988",
  "#CC3311",
  "#33BBEE",
  "#BE5F29",
  "#EE3377",
  "#8E958F",
  "#A6CEE3",
  "#33A02C",
  "#C97B7A",
  "#FDBF6F",
  "#CAB2D6",
  "#6A3D9A",
  "#9ACD32",
  "#40E0D0",
  "#737B94",
  "#AA5CAA",
  "#15742A",
  "#236AD3",
  "#445210",
  "#62F384",
  "#311535",
  "#803958",
  "#B4F2AA",
  "#1734B8",

];

export const ERROR_COLOR = "#FF8F7B"
export const WARNING_COLOR = "#ffefa4"
export const NOTICE_COLOR = "#addcaf"


export async function checkTaskCallback(callbackURL, {maxRetries = 100, delayMs = 200} = {}) {
  if (maxRetries <= 0) {
    throw new Error('Max retries reached. Stopping.');
  }

  try {
    const response = await fetch(callbackURL);
    if (response.status === 200) {
      return await response.json();
    }
    // If not 200, wait, decrement retry count, try again
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    return checkTaskCallback(callbackURL, {maxRetries: maxRetries - 1, delayMs});
  } catch (err) {
    console.error('Error fetching callback:', err);
    // Wait, decrement retry count, try again
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    return checkTaskCallback(callbackURL, {maxRetries: maxRetries - 1, delayMs});
  }
}


export const readyGreen = "#176114"
export const disconnectedGrey = "#585858"
export const lostRed = "#DE3618"
export const disabledColor = "rgba(0, 0, 0, 0.38)"
export const inactiveGrey = "#99999b"


export const stateDisplay = {
  "init":          {display: "Starting", color: readyGreen, backgroundColor: "#DDFFDC"},
  "ready":         {display: "On", color: readyGreen, backgroundColor: "#DDFFDC"},
  "sleeping":      {display: "Paused", color: disconnectedGrey, backgroundColor: null},
  "disconnected":  {display: "Off", color: disconnectedGrey, backgroundColor: null},
  "lost":          {display: "Lost", color: lostRed, backgroundColor: null},
  "NA":            {display: "Not available", color: disconnectedGrey, backgroundColor: null},
}

export function objectWithDefaultEmpty(obj) {
  /**
   * Wraps an object in a Proxy that returns an empty object `{}`
   * when accessing a missing top-level key, instead of `undefined`.
   *
   * Useful for safely reading from objects of objects without having to check
   * for existence before access.
   *
  **/
  return new Proxy(obj, {
    get(target, key) {
      if (key in target) {
        return target[key];
      }
      return {}; // return empty object for missing keys
    }
  });
}
