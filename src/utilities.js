
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



export function runPioreactorJob(unit, experiment, job, args = [], options = {}, callback) {
    fetch(`/api/workers/${unit}/experiments/${experiment}/jobs/${job}/run`, {
      method: "PATCH",
      body: JSON.stringify({ args: args, options: options }),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
    }).then(response => {
      if (callback && typeof callback === 'function') {
        callback(response);
      }
    });
}



export class DefaultDict {
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
  "#EE7733",
  "#EE3377",
  "#BBBBBB",
  "#a6cee3",
  "#1f78b4",
  "#b2df8a",
  "#33a02c",
  "#fb9a99",
  "#e31a1c",
  "#fdbf6f",
  "#ff7f00",
  "#cab2d6",
  "#6a3d9a",
  "#ffff99",
  "#b15928",
  "#9ACD32",
  "#40E0D0",
  "#4682B4",
  "#D473D4"
];