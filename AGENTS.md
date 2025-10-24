# Agent Guidelines for the Pioreactor Mono-Repo

This repository contains the **executable code for the Pioreactor project**. It has three primary sub-projects:

1. **`core/`** — backend / worker code that runs jobs
2. **`core/pioreactor/web/`** — Flask-based web API
3. **`frontend/`** — React-based web UI

---

## Running the System

**Startup order (recommended):**

1. Start the Huey consumer:

   ```bash
   make huey-dev
   ```
2. Start the web API (port **4999**):

   ```bash
   make web-dev
   ```
3. Start the React dev server (port **3000**):

   ```bash
   make frontend-dev
   ```
4. (Optional) Run Pioreactor jobs, e.g.:

   ```bash
   pio run XYZ
   ```

---

## Editing Rules (Important)

1. **Do not apply automatic formatting** — leave that to our linter.
2. Place custom/experimental code in **`scratch/`** only.
3. **Do not run `pre-commit`** or lint manually.
4. **Do not use Git commands unless asked** — I will manage version control.
5. **Do not delete any files** you didn’t create yourself.

---

## Tools & Commands

Available commands are listed in the `Makefile`. Key ones:

```bash
make tail-log       # Show last 10 lines of the merged pioreactor log (override with LINES=200)
make huey-dev       # Run Huey consumer with dev flags
make web-dev        # Run Flask API on 127.0.0.1:4999
make frontend-dev   # Run React dev server on 127.0.0.1:3000
```

---

## Testing

 * Use **pytest** for Python tests. However, all the tests take in excess of 30 minutes, so don't run the entire test suite. Instead run specific files or tests using pytest options.

  ```bash
  pytest core/tests/test_cli.py
  ```

 * To run just the web backend tests, use

  ```bash
  pytest core/tests/web/
  ```

---

## Logging

* All logs are written to **`pioreactor.log`**.
* To view logs:

  ```bash
  make tail-log
  ```

---

## Search & Navigation

When searching the repo:

* **Exclude** these directories:

  * `core/migration_scripts/`
  * `core/tests/data/`
  * `core/update_scripts/`

* **Exclude** all `CHANGELOG.md` files.


## Business logic

Make sure to consider the following when editing and reviewing code.

 - One of the Raspberry Pi's is assigned as the "leader", and this hosts most of the services: web server, MQTT broker, database, etc. It also sends commands to any "workers". The leader can also be a worker. Together, the leader and all the workers are called a "cluster". A cluster can be a small as a single leader+worker. Pioreactors are assigned to be a leader, worker, or both based on the custom image they install.
 - Different jobs, like stirring, OD reading, dosing, etc. are controlled by separate Python objects. Some jobs will passively listen for events from other jobs, and change their behavior in response, for example, dosing automations listen to OD readings, and may respond by dosing or not dosing.
 - The main "control plane" for the Pioreactor software is the command line interface, pio. For example, when the user starts a activity from the UI, the web server will run `pio run X ...`, which launches a Python process that will instantiate the object the controls the activity.
 - Because each activity is a separate Python process, we can modify an activity before running it by changing files on the filesystem.
 - The Raspberry Pis / Pioreactors communicate through the local network (in more advanced cases, this network is hosted on the leader). Users control the Pioreactor cluster while being on the same network, and accessing the web UI or the command line of the Pioreactors.
 - Leaders talk to Pioreactors via http requests between their respective web servers (using lighttpd + Flask, on port 80 by default). Workers send experiment data back to the leader via MQTT (see below). We expect users to control the leader only (using the web interface or CLI), and let the leader control the workers (there are exceptions).
 - The Pioreactor UI also connects to MQTT, and uses it to push and pull live data from the activities in each Pioreactor (states of activities, settings, graphs, etc).
