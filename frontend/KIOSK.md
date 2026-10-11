# Per-Pioreactor touchscreen ("kiosk") UI: notes

Status: the second iteration is underway in `frontend/kiosk.html` and
`frontend/src/kiosk/`, served under `/k/` (see "What's built so far").

Groundwork that doesn't depend on the kiosk lands on `develop` first, so the kiosk
diff stays about the kiosk ("make the change easy, then make the easy change"):

| Commit on `develop` | Change |
| --- | --- |
| `c8c57688f` | The leader's `/api` accepts cross-origin requests from cluster members (`web/cors.py`). |
| `e19b6e585` | Calibration session steps run as a Huey task: advancing answers `202` and clients poll the task. Zero W workers run two Huey workers. The main UI's session dialogs poll through `utils/calibrationSessions.js`. |
| `4d125316a` | The leader's `/api` rejects mutating requests whose `Origin` is neither the leader nor an allowlisted cluster origin (`403`). |

When this branch is rebased onto `develop`, take `develop`'s `cors.py`, `test_cors.py`
and `app.py` hook over the earlier copies in this branch's wip commit.

The October 2026 proof of concept was a lean, touch-first port of the cluster UI for a
5" landscape screen rendered by WPE on a Raspberry Pi. It has been removed from the
tree; its code (`frontend/display.html`, `frontend/src/display/`) is in git at commit
`249fb8ca3`. Its keyboard, value helpers, canvas chart and automation sheet were ported
into `src/kiosk/`.

## Product direction

Like a 3D printer farm, each Pioreactor gets its own screen:

1. Each Pioreactor (leader or worker) has a display controlling _most_ things, but
   scoped to that one Pioreactor: a "worker view".
2. The global UI (the default app in `frontend/`) still controls one or many
   Pioreactors. It is not changing.
3. A USB stick inserted into a Pioreactor (leader or worker) can export that
   Pioreactor's data only.
4. Experiment assignment is undecided. Perhaps the worker pulls the experiment list
   from the leader and the user picks one on the screen.

New APIs will likely be needed. Those are deferred. Make notes about what is needed.

## Requirements for the next iteration

1. Colour palette and design language close to the existing UI (`DESIGN.md`). Keep
   the chunky, touch-sized buttons from the POC.
2. No clock.
3. No Identify button.
4. Keep the left navigation rail.
5. Dark mode and Light mode. Ex: Use the existing UI's dark palette (`src/theme/colors.js`,
   `darkColors`; page background `#191A21`, surface `#22232B`, zebra `#292A34`,
   primary `#B9A5FF`, text `#F1F0F5`, secondary text `#BDBBC9`, border `#55535F`).
6. Aim for high performance and responsiveness.
7. The display runs at 1x scale (no `WPE_DRM_SCALE`) from now on.
8. Ignore deployment and packaging for now.
9. Pages live under a new prefix, `/k/`,

## Lessons from the POC

### Screen and sizing

- The test panel was a Raspberry Pi Touch Display 2, 5", 720x1280 native, rotated
  to landscape. At 1x that's a **1280x720 CSS viewport at roughly 290 ppi**, so 1 CSS
  px is about 0.09 mm. A 44 px target would be about 4 mm, far too small for a finger.
  Size targets physically (about 9-10 mm, roughly 100-110 CSS px at 1x) and set the
  root font size to match. The POC scaled everything in `rem` from a root size of
  `clamp(14px, 3.34vh, 22px)`. That holds the layout together, but the clamp range
  must change for a 1x, 290 ppi panel.
- The POC was designed at 800x480 and checked at 640x360 (the 2x-scaled panel) and at
  1024x600. Develop with the browser viewport set to the real CSS size.

### Interaction (touch on a laggy renderer)

- No hover states, tooltips, shadows, blurs, transitions or animations. Give feedback
  with `:active` and explicit pending states.
- WebKit applies `:active` on touch only if a `touchstart` listener exists. Add a
  passive no-op listener on `document`.
- Block `contextmenu` (long-press). Hide the pointer after a touch and show it again on
  mouse use.
- Act on **`pointerdown`** for keys that don't change what's on screen (keyboard
  characters), so a slow paint still feels instant. Use **`click`** for anything that
  closes an overlay or navigates, or the release lands on whatever was underneath.
- Start/Stop shows "Starting..."/"Stopping..." immediately, until MQTT reports the
  target state. After a timeout (15 s), clear it and show a toast pointing to Logs.
  Jobs can take several seconds to start, and some exit at once (for example, the
  thermostat with no heater in dev).
- After an edit, keep showing the submitted value until the confirmed value arrives
  over MQTT (with a short fallback timeout). Otherwise the field flickers back to the
  old value between the HTTP response and the MQTT echo.
- Confirm destructive actions (stop all, end experiment, reboot or shut down,
  unassign) with a dialog.

### Pop-up keyboard

- Use a full-screen editor, not a docked keyboard over the page. The label, the value
  with its caret, Cancel and Done stay visible, and nothing needs scrolling into view.
  Fields are buttons that open it. There are no native `<input>`s.
- Numbers: a big keypad (7-8-9 layout) with backspace (repeats when held), Clear, a ±
  key and a tall Done key. An optional row of presets (for example 0.5/1/2/5/10 mL).
  The first keystroke replaces a pre-filled value, like a selected field. Validate
  min/max/sign/integer and keep the keyboard open with the reason.
- Text: QWERTY plus a `?123` symbols page, one-shot shift (double-tap locks it), caret
  left/right and a custom `validate()`.
- A physical keyboard also works (Enter submits, Escape cancels). This is useful in
  development.

### Data and rendering performance

- Reuse the main app's data layer (`MQTTProvider`, `ExperimentProvider`,
  `RunningProfilesProvider`, `utils/jobs.js`, `utils/bioreactor.js`,
  `useExperimentChartPreferences`). The POC wrapped `subscribeToTopic` in two hooks:
  - `useTopicValues(patterns, throttleMs)`: latest payload per topic. Messages are
    batched into one state update per window (about 80 ms for the first burst of
    retained messages, then 0.6-1 s).
  - `useTopicStream(patterns, handler)`: every message, for logs and live charts.
- One wildcard subscription covers a unit: `pioreactor/<unit>/<exp>/+/+` brings every
  job's `$state` and published settings. It doesn't include logs, which have six
  levels.
- Pass primitive-only props to tiles and rows so `memo()` can skip unchanged ones.
- Use canvas charts, not SVG/Victory. Request about 600 points from
  `/time_series/...?target_points=...`. Buffer live points and redraw at most every 2 s
  (60 s when hidden). Thin old points so long sessions stay bounded. "Tap to read"
  replaces hover tooltips.
- Chart descriptors carry JS expressions (`lookback`, `y_transformation`). The main UI
  `eval`s them. Note that the dev config uses `*_lookback_minutes`, which makes the
  hours expressions NaN.
- OD charts are split by sensor. Series names are `<unit>-<channel>`, mapped to an
  angle via `[od_config.photodiode_channel]`, and `REF` channels are hidden.
- In dark mode, lift series colours with `lighten(color, 0.35)` (the same rule as
  `theme/useChartTheme.js`).
- WPE runtime cost to watch: MUI/emotion styling at runtime. The POC kept MUI only for
  icons and `MQTTProvider`'s error snackbar, and used plain CSS for everything else.
  Bundle size was not a concern; render cost is.

### Robustness (a kiosk has no address bar)

- `MQTTProvider` gives up if the *first* connection fails (3 quick attempts). A kiosk
  that boots before the broker is ready stays offline, so the POC reloads after 60 s
  if it never connected. Consider a proper retry in the provider instead.
- An error boundary shows Reload and "Back to Pioreactors", and reloads by itself
  after 60 s.
- Keep config loading retrying until the web server answers.
- **Never let the HTML shell be cached.** A cached page points at hashed assets that
  an update deleted, which gives a blank screen. The POC added `no-store` for
  `/static/display.html` in lighttpd. A `/k/` route needs the same treatment.

### API notes found along the way

- `GET /api/experiments/<exp>/recent_logs` caps `lines` at 100 (it returns 400 above
  that) and only returns the last 24 hours.
- `GET /api/workers/<unit>/automations/descriptors/<type>` took about 3 s in dev.
  Prefetch it when a unit page opens; `utils/jobs.js` caches it.
- `PATCH /api/workers/<unit>/jobs/update/...` opens a new MQTT client per request on
  the leader just to publish `.../<setting>/set` at QoS 1. On a Pi it may be faster to
  publish directly from the page's MQTT connection (the POC kept HTTP to match the
  main UI).
- `PUT /api/experiments/<exp>/workers` reassigns a worker from another experiment and
  stops its jobs there. The screen should confirm before doing that.
- The leader-side `X-Pioreactor-Target` header routes `/unit_api` calls (used for
  profiles).

### Tooling

- The second Vite entry (`display.html`) shares chunks with the main app. After
  adding new `@mui/icons-material` imports, the dev server's pre-bundled deps can go
  stale ("Element type is invalid... got: undefined"). Reload the page.
- lighttpd's SPA fallback sends every unknown path (including `/display` and `/k/...`)
  to `/static/index.html`. A `/k/` UI needs either routes in the main app or a lighttpd
  rewrite to a separate HTML entry.

## Decisions so far

| Topic | Decision |
| --- | --- |
| Data sources | Live data and cluster state come from the leader (MQTT broker, `/api`). Unit-local actions go through the worker's own `/unit_api`. Details are still being worked out; see the draft below. |
| USB export | The worker fetches its own rows from the leader and writes them to the USB stick. |
| Creating experiments | Only on the leader's screen. |
| Experiment assignment | Any screen can join, move to another experiment, or leave (unassign), including experiments other units are in. Moving and leaving name the jobs they will stop and need a danger confirmation. |
| Ending experiments | Only the leader's screen. (UI policy: the leader's `/api` doesn't check which screen asked.) |
| Leader's screen | Mostly its own worker view, plus a few leader-only abilities (experiment creation, profiles). Details are still being worked out; see the draft below. |
| In scope on every screen | Self-test, OD blank, pumps, LEDs, plugins' jobs (along with the core jobs and automations), and **calibrations at the bench**. |
| Out of scope on worker screens | Experiment profiles (leader screen only). |
| Viewing other units | The leader's screen probably does not open other units' views. |
| URL scheme | `/k/` with an implicit self (`/k/`, `/k/dosing`, `/k/charts`, ...), served by a separate HTML entry, `kiosk.html`. |
| Cross-origin access | Done on `develop`: the leader's `/api` accepts requests from cluster members' screens (`core/pioreactor/web/cors.py`). |
| Cross-site writes | Done on `develop`: mutating `/api` requests with a foreign `Origin` get `403`. An `Origin` check rather than requiring a JSON content type or custom header, so no existing client (body-less POSTs, uploads, scripts) had to change. |
| Code | Leaner code than the main app is fine where it helps responsiveness. It need not reuse `MQTTProvider`/MUI. |
| Access control | The lab is trusted: no screen lock. Destructive actions still ask for confirmation. |

## Draft: where a screen gets its data

Unit-local capabilities already exist on every Pioreactor's `/unit_api`:
- jobs: run, stop, descriptors, running
- automation descriptors
- bioreactor values
- calibrations and calibration sessions, estimators
- USB: list, mount, eject, artifacts
- config
- system: reboot, shutdown, clock, disk, memory, ipv4
- versions, health

Cluster-wide state (experiments, assignments, time series, logs, exports, labels) lives
on the leader.

| Need | Proposed source |
| --- | --- |
| Live job states and settings | Leader MQTT: `pioreactor/<self>/<exp>/+/+` |
| Which experiment this unit is in | Leader MQTT, retained: `pioreactor/<self>/$experiment/assignment` (published by the leader on every (re)assignment) |
| Start/stop jobs, job descriptors, automations | Local `/unit_api/jobs/...` (keeps working when the leader is down, as long as the experiment is known) |
| Change a running job's settings | MQTT publish to `pioreactor/<self>/<exp>/<job>/<setting>/set` (what the leader's PATCH endpoint does anyway) |
| Bioreactor values, calibrations, self-test, OD blank | Local `/unit_api` |
| Charts (history), logs, experiment list, labels | Leader `/api`, called directly from the screen (needs the CORS change below), filtered to this unit |
| USB export | Worker asks the leader for its own rows, writes them locally (new API) |

Open points:
- **Cross-origin access.** Done. See "Cross-origin access to the leader's API".
- **Leader address.** Done: the worker's own config (`cluster.topology.leader_address`,
  `mqtt.broker_address`) via `/unit_api/config/merged`. On the leader itself, calls stay
  same-origin.
- **Leader unreachable.** Done: while the broker is unreachable, Activities lists
  `/unit_api/jobs/running` (polled every 5 s, unit-local) with Stop buttons and says
  plainly that live readings are unavailable. The kiosk's MQTT client reconnects
  forever.
- **Which hostname is "self".** Done: `GET /unit_api/health` returns `pioreactor_unit`.
- **Which experiment.** Done: the retained `pioreactor/<self>/$experiment/assignment`
  message, plus one `GET /api/workers/<self>/experiment` on boot (and after each broker
  reconnect) for leaders that haven't published it yet.

## Cross-origin access to the leader's API

Implemented as planned below in `core/pioreactor/web/cors.py` (an `after_request`
hook registered on the leader only; tests in `core/tests/web/test_cors.py`), on
`develop`. Cluster hosts are cached in-process for 30 s rather than in `web/cache.py`:
the set is tiny and per-process memory avoids a disk read on every request. `https`
origins are accepted too, for leaders set up with HTTPS. The related cross-site POST
issue below is closed too (see the end of this section).

**Before.** A screen loads from its own unit (`http://localhost/k/...` on that unit), so
every call to the leader is cross-origin. lighttpd's `51-cors.conf` only covers
`/static/(css|js|media)/`, and Flask sets no CORS headers. So the browser:
- blocks reading any leader `/api` response;
- blocks every JSON request (`Content-Type: application/json` and `PATCH`/`PUT`/`DELETE`
  all need a preflight that nothing answers).

MQTT is unaffected: WebSockets aren't subject to CORS and mosquitto doesn't check
`Origin`. The screen can use the broker address from its own config. The display
runtime already ships the mDNS fix for resolving `*.local`.

**Yes, it's fixable, and cheaply.** Add CORS in Flask on the leader rather than in
lighttpd, because the allowed origins depend on the inventory:

- An `after_request` hook (leader only, paths under `/api/`) checks `Origin` against an
  allowlist and, on a match, adds:
  - `Access-Control-Allow-Origin: <that origin>` and `Vary: Origin`. Never `*`.
  - `Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS`.
  - `Access-Control-Allow-Headers: Content-Type, Accept, X-Pioreactor-Target`.
  - `Access-Control-Max-Age: 600`. Preflight caching matters on a slow screen: without
    it, every JSON write costs an extra round trip. WebKit caps the cache at 600 s.
- Preflights: Flask already answers `OPTIONS` for every route (automatic options), and
  lighttpd forwards `/api` (including OPTIONS) to FastCGI. The hook only adds headers.
  `after_request` also runs for error responses, so the screen can read error bodies.
- Allowlist:
  - `http://localhost` and `http://127.0.0.1` (any port), which is where each kiosk
    loads from;
  - for every worker in the inventory: `http://<unit>`, `http://<unit>.local` and
    `http://<ipv4_address>`.

  Cache the computed set briefly (`web/cache.py`) so each request doesn't hit the
  database. Allowing `localhost` is a small widening: any page served from a lab
  computer's own localhost could also call the leader. That's acceptable for a trusted
  lab. The alternative is loading kiosks from `http://<self>.local/k/` so each has a
  specific origin.
- No cookies or auth exist, so no `Allow-Credentials`.
- Client side: the screen resolves relative URLs the leader returns (for example
  Huey's `result_url_path`) against the leader's origin, not its own.
- Server-to-server traffic doesn't need CORS. USB export (worker Python asks the leader
  for its rows) and existing leader-to-worker fan-out are unaffected.
- Dev: the Vite proxy makes everything same-origin. To exercise CORS locally, serve
  the kiosk from another port (for example `127.0.0.1:3001`) and point it at
  `localhost:4999`.

Why not the alternatives:
- `Allow-Origin: *`: any website open on a lab computer could read cluster data and
  send JSON commands.
- A proxy on the worker (`/unit_api/leader/...`): adds a hop through the worker's
  single FastCGI app for every chart, log and experiment call. It's slower, and slow is
  what we're trying to avoid.

**Related, existing issue (not caused by this).** Mutating endpoints don't require a
JSON content type:
- `decode_request_body` parses `request.data` whatever `Content-Type` says;
- some routes take no body at all (for example
  `POST /api/workers/<unit>/jobs/stop/experiments/<exp>`).

So any web page open on a lab computer could trigger actions with a "simple"
cross-site POST that needs no preflight (it just can't read the response). CORS
doesn't change that.

**Closed on `develop`** with an `Origin` check (`reject_cross_site_writes` in
`cors.py`, a `before_request` hook): a mutating `/api` request that carries an
`Origin` must come from the leader itself (same host and port) or an allowlisted
origin, or it gets `403` before the handler runs. Browsers always send `Origin` on
cross-site requests; requests without one (scripts, `curl`, other Pioreactors) are
unaffected. Requiring a JSON content type or a custom header was the alternative, but
about 18 main-UI calls (body-less POSTs, file uploads), the MCP tools and `pio blink`
would have had to change. `/unit_api` has no such check yet.

## Draft: calibrations at the bench

Calibration sessions already run entirely on the unit (`/unit_api/calibrations/sessions`):
- start: `POST {target_device, protocol_name}`
- read: `GET .../<session_id>`
- advance: `POST .../<session_id>/inputs {inputs}`
- abort: `POST .../<session_id>/abort`

The protocols are `stirring_dc_based`, `pump_duration_based`, `od_standards`,
`od_fusion_standards`, `od_fusion_offset` and `camera_manual_focus`. Because sessions
are unit-local, calibrations work even when the leader is unreachable.

The screen needs a generic step renderer, like the main UI's
`CalibrationSessionDialog`:
- Step types: `info`, `confirm`, `form`, `action`, `result`.
- Field types:
  - `float` and `int`: number pad, with `minimum`/`maximum` and their error messages.
  - `string`: text keyboard.
  - `bool`: toggle.
  - `choice`: chunky option buttons.
  - `float_list`: a list editor with an add-value row (needed for OD standards).
- Charts: `step.metadata.chart` (title, axis labels, series). Reuse the canvas chart.
- Camera focus: show the preview from `/unit_api/camera/focus_sessions/<id>/preview.jpg`.
- Afterwards: list calibrations per device and set the active one (`/unit_api/calibrations`,
  `/unit_api/active_calibrations/<device>/<name>`), alongside estimators.

Things to handle:
- **Long action steps.** Done on `develop`: advancing a step runs
  `advance_calibration_session_task` (Huey) and answers `202`; poll `result_url_path`
  (`/unit_api/task_results/<id>`), whose `result` is `{session, step}`. That task waits
  on the hardware-action tasks, so consumers need at least two Huey workers (Zero W
  workers went from one to two). The screen shows a busy note with the step title and
  keeps Abort reachable; a step aborted while it runs keeps the abort.
- **Picking a protocol.** Use the protocol list per device (`/unit_api/calibration_protocols`)
  with the protocol descriptions (`calibrations/protocols/README.md`).

## Draft: experiment assignment from a screen

Decided (see "Decisions so far") and built:
- Any screen can join, reassign (move) or unassign (leave), including experiments other
  units are in. Reassigning and unassigning stop the unit's jobs, so they need a danger
  confirmation.
- Only the leader's screen creates experiments (name via the keyboard; creating doesn't
  assign anything) and ends them.

Still open: what the screen shows when the global UI reassigns it mid-use. Today the
page follows the retained assignment message without a banner.

## Draft: the leader's screen

Its own worker view, plus a small leader-only section:
- Create and end experiments: built, in the experiment sheet.
- Experiment profiles: run and stop. Does running one for the whole experiment from a
  worker-style screen make sense, or only for this unit?
- Possibly cluster-level power (reboot/shut down all) and a read-only "N units
  assigned" summary. No per-unit control of other Pioreactors.

## URL scheme (decided)

`/k/` with an implicit self, from a separate HTML entry (`kiosk.html`), so the screen
never loads the main app's bundle. In development, a Vite middleware serves
`kiosk.html` for `/k` and `/k/...`. Production needs a lighttpd rewrite from
`^/k(/.*)?$` to `/static/kiosk.html` (the main app's SPA fallback otherwise catches
`/k/...`) and a `no-store` rule for that shell; see "Next".

## Performance: where it will hurt

Ranked by expected impact. Nothing here has been measured on a worker yet. The POC
only ran on a Pi 4 (1 GB) leader.


### 3. Extra hops (mostly avoidable by choosing the right source)

- Use the unit's own `/unit_api` for anything unit-local: descriptors, job start/stop,
  calibrations, bioreactor values. The POC called leader routes like
  `/api/workers/<unit>/...`, which go screen → leader → worker → leader → screen. The
  automation-descriptor call took about 3 s that way, even in dev.
- Change settings by publishing `.../set` over MQTT directly. Avoid the leader's PATCH
  endpoint, which opens a fresh MQTT client per request.
- Charts and logs have to come from the leader's database. Fetch them once when a page
  opens, then follow live MQTT. Never poll.

### 4. Leader load as screens multiply

With N screens:
- MQTT is cheap for mosquitto (one WebSocket each, a handful of topics).
- HTTP isn't free: the leader runs a single FastCGI process (`max-procs 1`) with SQLite
  behind it, so chart-history queries from many screens queue behind the main UI's.

Keep screens off the leader except on page open, and use the per-unit time-series
endpoints (smaller queries).

### 5. Rendering (the POC's approach holds)

For a single unit, this is small:
- One wildcard subscription, batched state updates, canvas charts.
- No shadows, animations or MUI styling at runtime.
- Going from 2x to 1x doesn't change the device-pixel count (1280x720 either way), so
  fill cost is the same.
- JS parse/compile happens once at boot.

## What's built so far

`frontend/kiosk.html` + `frontend/src/kiosk/`. Checked in dev at 1280x720, light and
dark, against the dev leader (job start/pause/resume/stop, setting edits over MQTT,
automation start sheet, live logs, experiment sheet, cross-origin GET/PUT).

- **Shell.** Left rail (Control, Charts, Calibrations, Logs, System) and a top bar
  with the page title, this unit's name (with the Pioreactor icon) and an experiment
  chip. No clock, no Identify,
  no connection indicator (pages say when the leader is unreachable). Root size `clamp(14px, 4.17vh, 34px)` (30 px at 720 tall);
  targets are at least 3.4rem (about 9 mm on the panel).
- **Runtime cost.** No MUI or emotion: icons are the same paths as the main UI's,
  drawn as plain SVG. The kiosk's own JS chunk is about 59 kB (21 kB gzipped) plus
  React. One MQTT connection; a handler joining an already-subscribed pattern gets the
  last payloads replayed, since the broker sends retained messages only once.
- **Boot.** Retries `/unit_api/health` and `/unit_api/config/merged` until the web
  server answers; an error boundary reloads after 60 s.
- **Control** (the Activities page) has three tabs: Activities (`/k/`), Dosing
  (`/k/dosing`) and LEDs (`/k/leds`), with Stop all (confirmed) beside them.
  - Activities: descriptor-driven job rows (including plugins' jobs) with Start,
    Pause/Resume, Stop and editable settings, the automation start sheet, and Self-test
    / OD blank buttons. Start, stop and descriptors use the local `/unit_api`;
    pause/resume and setting edits publish `.../set` over MQTT.
  - Dosing: vial values (edited via local `PATCH /unit_api/bioreactor/...`) and pumps
    with volume presets. The unit itself refuses overfilling.
  - LEDs: per-channel intensity with presets; all off.
- **Calibrations** (`/k/calibrations`), all unit-local: a device list (with each one's
  active calibration), and per device its protocols, saved calibrations (tap for the
  curve; set or clear active) and estimators (set or clear active).
  - Starting a protocol shows its description and requirements.
  - A session runs full-screen, one step at a time: text, images (first loading frame
    only, no animation), guidance, tables, fields (number pad with the protocol's
    min/max messages, text, yes/no, choices, a list editor for `float_list`) and an XY
    canvas chart. Long action steps show a busy note while Abort stays reachable. The
    runner follows a `202` task answer (`waitForTask` in `api.js`) and still accepts a
    direct `200`, so it works before and after the rebase onto `develop`.
  - The session id is kept in `localStorage`, so a reload resumes the session.
  - Checked in dev: a full stirring DC-based run.
- **Charts.** Leader chart descriptors and this experiment's Pioreactor-page
  preferences; per-unit time series from the leader, then live MQTT. Canvas, tap to
  read.
- **Logs.** This unit's recent logs from the leader plus live MQTT (experiment and
  `$experiment` logs); add a note.
- **System.** Name, address, version, storage, memory, and the leader (workers only,
  with "unreachable" when it is); Light/Dark; reload; reboot and shut down (confirmed,
  via local `/unit_api/system/...`).
- **Experiment sheet** (the top bar's experiment chip): shows the assignment. An
  unassigned unit can join an experiment; an assigned one can move to another
  (`PUT /api/experiments/<exp>/workers`) or leave (`DELETE .../workers/<self>`), both
  behind a danger confirmation that its running jobs will stop. The leader's screen
  also has End
  experiment (`DELETE /api/experiments/<exp>/workers`, the main UI's "End experiment"),
  whose confirmation names every assigned unit, and New experiment: a name typed on
  the keyboard (checked against the leader's naming rules), then
  `POST /api/experiments`. Creating doesn't assign the leader; the new experiment
  appears in the list to assign like any other.

Jobs started from the screen get the same env the leader adds (`EXPERIMENT`,
`ACTIVE`, `MODEL_NAME`, `MODEL_VERSION`) when the leader's worker record is known, so
the job doesn't have to ask the leader for them.

## Next

Known, not yet done:
- **Serving `/k/` in production**: the lighttpd rewrite and `no-store` rule above (the
  POC's `display.html` rule was removed from `10-expire.conf`), and pointing the
  display runtime (`packaging/experimental/display/`, still set to
  `/static/display.html`) at `http://localhost/k/`. Deferred with packaging.
- **Self-test results.** The screen shows that a self-test is running and points to
  Logs; it doesn't summarize the published test results yet.

Waiting on decisions: USB export and local data on each Pioreactor (see the draft
below), and the leader-only section (create experiment, profiles, cluster power).

## Draft: local data on each Pioreactor

Proposed alongside USB export: each Pioreactor also keeps its own data, for recovery if
the leader is lost and so a USB stick can be filled without the leader.

Today:
- Workers publish over MQTT to the leader's broker; only the leader's
  `mqtt_to_db_streaming` writes rows (one SQLite database).
- Each job's MQTT client queues at most 100 messages in memory
  (`max_queued_messages_set(100)` in `pubsub.py`). A broker outage longer than a few
  minutes, or a job restart during one, loses readings.
- `backup_database` copies a full snapshot of the leader's database to
  `number_of_backup_replicates_to_workers` workers (2 in the example config). The
  generic Linux leader's timer runs it monthly, so recovery can lose weeks.
- The export request (`ExportDatasetsRequest`) has no per-unit filter.

Options:
- **A. Mirror after the broker.** Each worker runs the same streaming job, subscribed to
  `pioreactor/<self>/#`, into a local SQLite with the same tables. Reuses the parsers
  and the export machinery (export from the local database). Survives losing the
  leader's disk, but not a broker outage: nothing arrives while the broker is down.
- **B. Record at the source.** Jobs also write what they publish to a local database,
  batched. Covers broker outages too, which is the point of recovery. More invasive:
  several processes writing one SQLite on an SD card.
- Later, either way: rebuilding a lost leader's database by merging workers' databases.


## Still open

- Which `/api` endpoints need unit-scoped variants (time series, logs and export
  already have some `/workers/<unit>/...` forms).
