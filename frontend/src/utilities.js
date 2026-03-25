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
            const paramMatch = line.match(regex.param);
            if(section){
                value[section][paramMatch[1]] = paramMatch[2];
            }else{
                value[paramMatch[1]] = paramMatch[2];
            }
        }else if(regex.section.test(line)){
            const sectionMatch = line.match(regex.section);
            value[sectionMatch[1]] = {};
            section = sectionMatch[1];
        }else if(line.length === 0 && section){
            section = null;
        };
    });
    return value;
}


export function getConfig(setCallback) {
  fetch("/api/config/files/config.ini")
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
    .catch((_error) => {})
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



export function runPioreactorJob(unit, experiment, job, args = [], options = {}, configOverrides = []) {
    return fetch(`/api/workers/${unit}/jobs/run/job_name/${job}/experiments/${experiment}`, {
      method: "PATCH",
      body: JSON.stringify({
        args: args,
        options: options,
        env: {EXPERIMENT: experiment, JOB_SOURCE: "user"},
        config_overrides: configOverrides,
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


// Use when you already have a result_url_path from a task response.
export async function checkTaskCallback(callbackURL, {maxRetries = 150, delayMs = 100} = {}) {
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


// Use when calling an endpoint that returns a task response with result_url_path.
export async function fetchTaskResult(endpoint, {fetchOptions = {}, maxRetries = 100, delayMs = 50} = {}) {
  const response = await fetch(endpoint, fetchOptions);
  if (!response.ok) {
    let message = `HTTP error! Status: ${response.status}`;
    try {
      const payload = await response.json();
      if (payload?.error) {
        message = payload.error;
      }
    } catch (_error) {
      // ignore JSON parse errors and fall back to default message
    }
    throw new Error(message);
  }
  const payload = await response.json();
  if (!payload.result_url_path) {
    if (payload?.error) {
      throw new Error(payload.error);
    }
    throw new Error('No result_url_path in response');
  }
  return checkTaskCallback(payload.result_url_path, {maxRetries, delayMs});
}

const BIOREACTOR_CONFIG_KEYS = {
  current_volume_ml: "initial_volume_ml",
  max_working_volume_ml: "max_working_volume_ml",
  alt_media_fraction: "initial_alt_media_fraction",
};

export function parseNumericValue(value) {
  const parsed = parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function getBioreactorFallbackValue(config, key) {
  const configKey = BIOREACTOR_CONFIG_KEYS[key];
  const parsedConfigValue = parseNumericValue(config?.bioreactor?.[configKey]);
  if (parsedConfigValue !== null) {
    return parsedConfigValue;
  }

  if (key === "alt_media_fraction") {
    return 0;
  }

  return 14;
}

export function getBioreactorConfirmedValue(values, config, key) {
  return parseNumericValue(values?.[key]) ?? getBioreactorFallbackValue(config, key);
}

export function getBioreactorSubscriptionTopics(unit, experiment) {
  const baseTopics = [
    `pioreactor/${unit}/${experiment}/bioreactor/current_volume_ml`,
    `pioreactor/${unit}/${experiment}/bioreactor/max_working_volume_ml`,
    `pioreactor/${unit}/${experiment}/bioreactor/alt_media_fraction`,
  ];

  return [
    ...baseTopics,
    ...baseTopics.map((topic) => topic.replace(`/${experiment}/`, `/_testing_${experiment}/`)),
  ];
}

export async function getBioreactorDescriptors() {
  const response = await fetch("/api/bioreactor/descriptors");
  if (!response.ok) {
    throw new Error(`HTTP error! Status: ${response.status}`);
  }
  return response.json();
}


export async function updateBioreactorValues(unit, experiment, values) {
  const response = await fetch(`/api/workers/${unit}/bioreactor/update/experiments/${experiment}`, {
    method: "PATCH",
    body: JSON.stringify({values}),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
  });

  if (response.ok) {
    return response.json();
  }

  let message = `Error ${response.status}.`;
  try {
    const payload = await response.json();
    if (payload?.error) {
      message = payload.error;
    }
  } catch (_error) {
    // ignore JSON parse errors and keep the default message
  }
  throw new Error(message);
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
