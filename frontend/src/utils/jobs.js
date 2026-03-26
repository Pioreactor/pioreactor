export function runPioreactorJob(
  unit,
  experiment,
  job,
  args = [],
  options = {},
  configOverrides = [],
) {
  return fetch(`/api/workers/${unit}/jobs/run/job_name/${job}/experiments/${experiment}`, {
    method: "PATCH",
    body: JSON.stringify({
      args,
      options,
      env: { EXPERIMENT: experiment, JOB_SOURCE: "user" },
      config_overrides: configOverrides,
    }),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
  })
    .then((response) => {
      if (response.ok) {
        return;
      }
      throw new Error(`Error ${response.status}.`);
    })
    .catch((error) => {
      throw error;
    });
}

export function runPioreactorJobViaUnitAPI(job, args = [], options = {}) {
  return fetch(`/unit_api/jobs/run/job_name/${job}`, {
    method: "PATCH",
    body: JSON.stringify({ args, options }),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
  })
    .then((response) => {
      if (response.ok) {
        return;
      }
      throw new Error(`Error ${response.status}.`);
    })
    .catch((error) => {
      throw error;
    });
}
