
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



export function runPioreactorJob(unit, job, args = [], options = {}, callback) {
    fetch(`/api/workers/${unit}/jobs/${job}/run`, {
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
