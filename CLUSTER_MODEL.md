# Cluster model: open questions

Status: draft for discussion. Giving every Pioreactor its own screen (see
`frontend/KIOSK.md`) changes what a single Pioreactor is expected to do on its own.
This file collects the questions that raises, groups them by the few decisions they
depend on, and records answers as we make them. `KIOSK.md` stays about the screen.

The screen ships with a v2 Pioreactor, so changing today's software rules (and choosing
v2 hardware to suit them) is in scope. The baseline below is where we start, not a
constraint.

## The picture so far

The 80% solution these decisions describe (details in "Decisions" below):

1. **Out of the box, every v2 Pioreactor is standalone:** a one-unit cluster with its
   own broker, database, global UI and screen.
2. **A cluster forms from the leader.** The leader (its screen or the global UI) lists
   standalone units nearby and adds them. Added units become workers. A worker leaves
   from either side and becomes standalone again. Joining and leaving happen only
   between experiments.
3. **Experiments are print jobs.** They usually span several units and belong to the
   leader. A unit is busy while assigned; moving it off the network then is
   unsupported. Reassigning within the cluster is fine.
4. **The leader's screen runs the cluster:** create experiments, assign units, run
   profiles, and see a status tile per unit. A laptop is optional. Each unit's screen
   controls only that unit.
5. **Accidental outages don't stop the bench.** If the leader drops mid-experiment, a
   unit's screen keeps full local control, and its data is buffered and sent when the
   leader returns.
6. **One global UI per cluster.** A worker's address redirects to the leader's UI.
7. **Losing the leader:** restore the latest backup onto another unit, which becomes
   the leader.
8. **Kept simple:** no RTC (time from the network), no bench lock (changes from
   elsewhere just appear live), and an ended experiment returns the unit to idle.

## Today's baseline

Facts the questions below start from:

- **The leader hosts everything shared:** the MQTT broker, the database, the web UI,
  the experiment list and the assignment table.
- **A worker asks the leader for its experiment.** `whoami.get_assigned_experiment_name`
  calls `GET /api/workers/<unit>/experiment` (6 retries) unless `EXPERIMENT` is set in
  the env. Without the leader, a new job can't start (the kiosk works around this by
  passing `EXPERIMENT`).
- **Only the leader stores data.** Jobs publish to the leader's broker, and only the
  leader's `mqtt_to_db_streaming` writes rows. Each job's MQTT client queues at most 100
  messages (`pubsub.py`), so readings during a longer outage are lost.
- **Jobs already running survive a leader outage.** They are separate processes on the
  unit. They keep controlling the hardware; their data just goes nowhere.
- **Config is pushed from the leader** (`pios sync-configs`). Calibrations and
  estimators already live on the unit.
- **Time comes from the leader.** Adding a worker points its chrony at the leader
  (`add_new_pioreactor_worker_from_leader.sh`). A Pi 4 / Zero 2 has no battery-backed
  clock, so a unit that reboots away from the network has the wrong time.
- **Roles are chosen at flash time.** The image decides leader vs worker. Workers join
  from the leader (UI or `pio workers add`), which SSHes into them.

## The root decision: is the leader a dependency or a coordinator?

Most questions below are really this one.

| Model | Summary | Cost |
| --- | --- | --- |
| 1. Leader-centric (today) | Units are peripherals of the leader. One database, one truth. | A unit off the network is degraded or blind. |
| 2. Autonomous units, leader aggregates (the 3D printer farm) | Each unit can run and record on its own. The leader collects, coordinates and shows the whole cluster. | Local data, local experiment identity, and a sync/reconcile story. |
| 3. Peers | No special leader, or an elected one. | Much more complex. Probably not. |

### Experiments are print jobs

Like a 3D printer during a print, a Pioreactor stays in its cluster for the whole of an
experiment. Deliberately taking it off the network mid-experiment is unsupported:
expect things not to work. Between experiments, a unit can leave and come back, or go
elsewhere.

- This is about the network, not about experiments: reassigning a unit to another
  experiment mid-experiment (inside the cluster) is still allowed.
- So the leader stays the authority during an experiment (model 1 or a light model
  2), and autonomy matters only for accidental outages (S1, S2, S5) and between
  experiments (D).

### Autonomy ladder

"Can a worker leave the network and still work?" means different things. Pick a rung:

| Level | A unit away from the leader can... | Today |
| --- | --- | --- |
| L0 | keep running jobs it already had | Yes |
| L1 | keep **recording** data, and backfill the leader when it returns | No (100-message queue) |
| L2 | start/stop jobs and change settings from its screen | Partly (kiosk: start/stop via `/unit_api`; no live data without the broker) |
| L3 | start a **new experiment** and reconcile it with the leader on return | No |
| L4 | be a standalone Pioreactor, and later join a cluster bringing its history | No |

Each rung needs the ones below it. L1 is the big one: without it, "still works" means
"keeps dosing, but the record has a hole".

Since experiments typically span several units (see Decisions), L3 is worth little: an
experiment started by one unit away from the others is a one-unit experiment. The real
choice is among L0, L1 and L2 (with L4 as an unboxing question, see D1).

### Scenarios to decide the rung

From a unit's point of view, "I left the leader" and "the leader left me" are the same
event. Which of these must work?

| # | Scenario | Needs |
| --- | --- | --- |
| S1 | The leader reboots for an update during a 3-day run (minutes away) | L1 |
| S2 | Flaky Wi-Fi drops a unit for a few minutes, several times a day | L1 |
| S3 | The leader's SD card dies mid-experiment (hours to days away) | L1, plus local data or a fast leader replacement (C3, D5) |
| S4 | ~~A unit is carried off the network mid-experiment and adjusted there~~ | Out of scope: experiments are print jobs |
| S5 | A unit reboots while the leader is unreachable (power blip) | L1 and a correct clock (A3) |
| S6 | Someone wants a single Pioreactor on a desk, no cluster | L4 (or today's leader+worker image), between experiments |

S1, S2 and S5: covered by "full local control" on an accidental outage (data
buffered and sent on return). S3: by restoring a backup onto a new leader (D5).

## Questions by area

### A. Autonomy and connectivity

1. ~~Which rung is the target?~~ Decided: on an accidental outage during an
   experiment, full local control (L2). Deliberate moves are unsupported.
2. While away, where does data go?
   - **Local broker with a bridge.** Each unit runs mosquitto; jobs publish to
     `localhost`; a bridge forwards `pioreactor/<self>/#` to the leader and queues while
     disconnected. Gives L1 with little new code, and the screen reads live data from
     its own broker, so L2 works offline too. Open: queue limits and persistence on the
     SD card, QoS of high-rate topics, and ordering on replay.
   - **Local database** (options A/B in `KIOSK.md`, "Draft: local data on each
     Pioreactor"). Also enables USB export and leader recovery.
   - These combine: the bridge for delivery, a local database for history.
3. Clock: no RTC on v2 (decided), so time comes from the network (the leader's
   chrony). During an experiment the unit is in its cluster, so this mostly holds. The
   gap is S5: a unit that reboots while the leader is down starts from
   `fake-hwclock`'s last saved time. Options: refuse to start jobs until the clock
   syncs, or mark readings "unsynced" and correct on return.
4. On reconnect: does the leader backfill silently, show the gap, or both? Is a
   setting changed on both sides during the outage resolved by last-writer-wins?
5. A unit moved to another room or network: does it look for its old leader, or can it
   meet a different one?

### B. Experiments

1. Is an experiment a cluster object (lives on the leader; units join it) or can a
   unit own one?
2. Who can create one? Decided: the leader's screen or the global UI. A laptop is
   optional, so the leader's screen must be able to set up a whole multi-unit
   experiment (create it and add units).
3. If a worker creates one while the leader is reachable, it's a `POST` to the leader,
   so it appears in every screen's list like any other. Is that wanted, or should a
   worker-created experiment be private to it until someone else joins?
4. Creating while away (L3): forbid it, or create it locally with a collision-free name
   and register it on return? What if the name was taken meanwhile?
5. ~~What's the common case: one unit per experiment, or many?~~ Several (see
   Decisions). So experiments are cluster objects that the leader owns, and B1 leans
   that way too.
6. Ending, renaming, notes and profiles: leader-only, or the owner's?
7. What does a screen show when the global UI reassigns its unit mid-use? (Open in
   `KIOSK.md`.)

### C. Data

1. Source of truth for readings: the leader's database only, or each unit's too?
2. USB export from a unit: from local data (works alone) or from the leader (needs
   it)?
3. Recovery when the leader's SD card dies: rebuild from units' local data, or rely on
   backups (today: full snapshots to 2 workers, monthly on the generic Linux leader)?
4. Disk budget and retention on a 32 GB card, per unit.

### D. Roles, membership and unboxing

1. ~~Is the first Pioreactor automatically the leader?~~ Decided: standalone until
   joined. Options were:
   - **Today:** the image decides.
   - **One image, role on first boot:** the screen asks "Start a new cluster" or "Join a
     cluster on this network" (leaders found by mDNS). A unit with no screen falls back
     to today's flow.
   - **Standalone first:** every unit boots as its own leader+worker (a cluster of
     one). Joining another cluster demotes it to a worker. Fits L4.
2. ~~Who approves a join?~~ Decided: units are added from the leader (its screen or the
   global UI), like today's "Add Pioreactor". Standalone units advertise themselves; the
   leader lists the ones it finds. Nothing happens on the joining unit's screen. A busy
   (assigned) standalone unit can't be added.
2a. What happens to a standalone unit's own history when it joins? No preference yet.
   Lean (cheapest, least surprising): it stays on the unit, read-only and
   USB-exportable, and isn't merged. Merging into the leader can come later.
3. Several clusters on one network: how does a new unit pick, and how is that shown?
4. Leaving a cluster: decided, from either side (the leader, or the worker's own
   screen), between experiments only. The unit keeps its calibrations and its
   `unit_config.ini`. Still open:
   - Which shared config it uses. Lean: keep the last copy synced from the leader as
     its own shared config, but rewrite the keys that point at the old leader
     (`cluster.topology.leader_hostname`/`leader_address`, `mqtt.broker_address`) to
     itself. The alternative is resetting the shared config to factory defaults.
   - What the leader shows for a unit that left while it couldn't reach it.
5. ~~Leader replacement?~~ Decided: restore the latest backup onto another unit, which
   becomes the leader, and workers find it again. Implies much more frequent backups
   (today: monthly on the generic Linux leader) and a way for workers to re-point to
   the new leader.
6. Mixed clusters: units without screens (and older hardware) must keep working with
   whatever we pick. Is that a hard constraint?

### E. Config, calibrations, plugins and updates

1. ~~Config: may a screen edit its own unit's config?~~ Decided: yes. A worker's screen
   edits its `unit_config.ini`; the leader's screen also edits the shared `config.ini`.
   `unit_config.ini` lives on the unit; `pios sync-configs` only pushes the shared
   `config.ini` and pulls a snapshot of `unit_config.ini` into the leader's
   `config_files_histories`. So a screen edit isn't overwritten; the leader's history
   just lags until the next sync. Optional: refresh that snapshot after a screen save.
2. Calibrations: already unit-local. Should the leader keep copies (for recovery and
   the global UI)?
3. ~~Plugins and updates: per unit or cluster-wide?~~ Decided: as today, the user
   chooses cluster-wide or per unit.
4. ~~Can a unit update itself from its screen?~~ Decided: yes. Mixed versions in one
   cluster are supported; the screen (and the global UI) warn when a unit's version
   differs from the leader's.

### F. Two control surfaces on one unit

1. The global UI and the unit's screen both control the same unit. Last writer wins,
   or a "in use at the bench" lock or notice?
2. Which actions are screen-only, leader-only, or both? (`KIOSK.md` "Decisions so far"
   has the start of this policy.)
3. Does a unit's screen show anything about other units (alerts, a cluster summary)?

### G. v2 hardware choices that settle software questions

1. ~~A battery-backed RTC~~ Not on v2 (decided). See A3.
2. Storage size and type (SD vs eMMC/NVMe) per unit: sets how much local data and
   broker queue a unit can keep (A2, C4).
3. ~~Which Pi?~~ Decided: Pi 4 and Pi 5 only. Every unit must run the full leader
   stack plus WPE when standalone; the POC already ran on a 1 GB Pi 4 leader. As a
   worker, a unit can turn off leader-only services (database writer, global UI) and
   keep its broker and screen.

### H. Trust and access

1. The lab is trusted today (no auth, no screen lock). Does more autonomy, or joining
   by pairing, change that?

## Consequences of the decisions so far

- **Every v2 unit can be a leader.** Standalone-first means each unit ships with the
  broker, database and web UI running. The hardware must carry that plus the screen.
- **A worker keeps its own broker after joining.** It's already there from standalone
  mode. Jobs and the screen use the local broker, and a bridge forwards to the leader
  and buffers during outages. This is the L1/L2 data path (A2), at little extra cost.
  Invariant: **jobs and the screen always talk to `localhost`**, whatever the role.
  Only the bridge knows where the leader is. Joining a cluster adds the bridge;
  leaving removes it. `mqtt.broker_address` stops depending on the role.
- **Joining and leaving happen between experiments only** (a unit is busy while
  assigned).
- **The leader's screen gets cluster abilities:** create experiments, add units to the
  cluster, assign and unassign units, run profiles, and a compact status tile per unit.
  Controlling another unit's jobs stays on that unit's screen or the global UI. This
  replaces the `KIOSK.md` note that the leader's screen doesn't open other units'
  views.
- **One global UI per cluster.** A worker's web address redirects to the leader's UI,
  focused on that unit. A worker still serves `/k/` (its screen) and `/unit_api`.

## Software changes

Sizes are rough: **XS** under a day, **S** a few days, **M** one to two weeks, **L**
several weeks. "Today" means it can ship in a normal release on current hardware,
before v2, and is useful on its own ("make the change easy, then make the easy change").
CustoPiZer (outside this repo) owns image builds, so image-level items also need work
there.

### What the code already gives us

- **Role is already decided by config, not by the image.** `whoami.am_I_leader()`
  compares the hostname with `cluster.topology.leader_hostname`, and `web/app.py`
  registers `/api` and `/mcp` only on the leader. The images differ in which services
  and packages they install.
- **Jobs' broker address is already separate from the leader's address**
  (`mqtt.broker_address` vs `cluster.topology.leader_address`). Pointing a worker's
  jobs at a local broker is a config change.
- **Jobs publish at QoS 2 by default** (`BackgroundJob.publish`), which a persistent
  bridge can queue and replay.
- **Units already advertise themselves** over mDNS (`_pio-worker._tcp`), and the leader
  lists unadded ones (`GET /api/workers/discover`).
- **The leader already publishes a retained assignment message per unit**
  (`pioreactor/<unit>/$experiment/assignment`, `publish_worker_experiment_assignment`
  in `web/api.py`).
- **A unit can already edit its own `unit_config.ini`** (`PUT /unit_api/config/specific`),
  **update itself** (`POST /unit_api/system/update`), report versions
  (`/unit_api/versions/app`) and be zipped and restored
  (`/unit_api/zipped_dot_pioreactor`, `/unit_api/import_zipped_dot_pioreactor`).

### Today: the easy changes

Ordered by value now, not by v2 dependency.

| # | Change | Size | Files | Helps today | Sets up for v2 |
| --- | --- | --- | --- | --- | --- |
| T0 | **The unit owns its model.** See "Sketch: the unit owns its model" below. | M | `whoami.py`, `web/unit_api.py`, `web/api.py`, `cluster_management/__init__.py`, `background_jobs/monitor.py`, `actions/leader/experiment_profile.py`, `structs.py` | Safety limits (max temperature, max fill) and hardware layout stop depending on the leader answering | A standalone unit knows its model; adding it needs no model picker |
| T1 | **Local membership record on each unit.** A job starting on a worker asks the leader three things over HTTP: its experiment, whether it's active, and its model (`whoami.py`). The model moves to the unit (T0). Cache the other two on the unit (`local_persistent_storage`), filled from the retained assignment message (extend its payload with `is_active`) and refreshed when the leader answers. `whoami` reads env, then the leader, then the cache when the leader is unreachable. | S-M | `whoami.py`, `web/api.py` (payload), a subscriber in `background_jobs/monitor.py` | Jobs start, and the kiosk works, while the leader reboots (S1) | The "full local control" decision needs exactly this |
| T2 | **A bigger MQTT client queue.** `max_queued_messages_set(100)` in `pubsub.py` covers well under a minute of a busy job. Raise it (a few thousand messages is still small) so a leader reboot doesn't drop readings. In memory only: a job restart during the outage still loses them. | XS | `pubsub.py` | S1, S2 lose less data | A stopgap until the bridge (V2) |
| T3 | **Frequent backups and a restore-leader flow.** Back up after each experiment ends and nightly instead of relying on a 30-day warning, to the configured workers. Add "restore this backup and become leader" (and a CLI). | M | `actions/leader/backup_database.py`, `background_jobs/monitor.py`, timers in `packaging/`, CustoPiZer | Recovery from a dead leader card today | D5 decision |
| T4 | **A cluster id.** The leader generates a UUID once, stores it in the shared config (pushed to workers), and advertises it. | S | `config.py`, `cluster_management/`, an update script | Telling clusters apart in `pio workers discover`; diagnostics | Workers re-find a restored leader under a new address; several clusters on one network |
| T5 | **Richer mDNS adverts.** TXT records on `_pio-worker._tcp` (model, version, cluster id or "none", assigned or idle), and a `_pio-leader._tcp` advert from leaders. | S | `utils/networking.py`, avahi service files (CustoPiZer), `GET /api/workers/discover` | The "Add Pioreactor" dialog can show model and version, and hide units already in another cluster | The leader's "units nearby" list; workers finding their leader |
| T6 | **A worker's web root redirects to the leader's UI** (`/pioreactors/<self>`). Today a worker serves the same SPA, which can't reach `/api` on it. | S | `web/app.py` (or lighttpd), `packaging/runtime-files/lighttpd/` | Users who open a worker's address land somewhere useful | Decided behaviour |
| T7 | **Version-mismatch warning** in the global UI's inventory (and the kiosk's System page): this unit's version differs from the leader's. | XS-S | `frontend/src/` inventory page, `src/kiosk/` | Mixed clusters are common after partial updates | Decided behaviour |
| T8 | **Clock-sync check.** A unit that boots while the leader is down starts from `fake-hwclock`'s last saved time. Check chrony's sync status before starting jobs (warn, or mark the job) and show it on the screen. | S | `background_jobs/monitor.py`, `unit_api.py` (`/system/utc_clock`) | Wrong timestamps after a power blip during a leader outage | Required: no RTC on v2 |
| T9 | **HTTP join and leave, instead of SSH with a password.** `/unit_api/cluster/join` (leader address, cluster id, shared config, the leader's SSH key, chrony server) replaces most of `add_new_pioreactor_worker_from_leader.sh`; `/unit_api/cluster/leave` generalises `cleanup_after_inventory_removal` (keeps calibrations and `unit_config.ini`, re-points the shared config at itself). Join is only accepted while the unit isn't in a cluster. | M | `packaging/runtime-files/bash/add_new_pioreactor_worker_from_leader.sh`, `cluster_management/__init__.py`, `web/unit_api.py`, `web/tasks.py` | No default password needed; fewer failure modes when adding | Add-from-leader and leave-from-either-side |
| T10 | **Role-gated services.** Make every leader-only service (database writer, backups, main UI) start only when `am_I_leader()` is true (for example `ExecCondition=pio is-leader`), even while two images exist. | S-M | `packaging/runtime-files/systemd/`, CustoPiZer | Little | Switching role becomes "change config, restart"; the single image (V1) is then packaging |
| T11 | **Origin check on `/unit_api`**, like the one on the leader's `/api` (open item in `KIOSK.md`). | S | `web/cors.py`, `web/app.py` | Closes cross-site writes to units | Every unit serves a screen and a UI |

**Tickets** (tag `kiosk-groundwork`): T0 `pio-20wc`, T1 `pio-3q8x`, T2 `pio-3esz`,
T4 `pio-a2mt`, T6 `pio-iigk`, T7 `pio-c4lk`, T8 `pio-idiz`, T11 `pio-lfoz`.

**Deferred** as larger risk:
- T3 (frequent backups, restore-leader): backups copy the whole database to workers
  (I/O and SD wear on a Pi, possibly during experiments), and restore is a new,
  high-stakes flow.
- T5 (mDNS TXT records, leader advert): avahi service files live in CustoPiZer, so it
  needs image changes and update scripts on every unit.
- T9 (HTTP join/leave): replaces a working onboarding flow, and an unauthenticated join
  endpoint needs a security design. Related: `pio-w6qy`.
- T10 (role-gated services): systemd changes on every install; a mistake leaves a
  leader's services stopped.

The main UI already has T7's warning (`Inventory.jsx`), so T7 covers the kiosk only.

### Today, behind a flag: the bridge

| # | Change | Size | Files |
| --- | --- | --- | --- |
| V2 | **Local broker + bridge on workers.** Every worker runs mosquitto; jobs and the kiosk use `localhost`. A persistent bridge (`cleansession false`, persistence on, generous `max_queued_messages`) forwards `pioreactor/<self>/#` both ways, plus the broadcast topics workers listen to (`pioreactor/$broadcast/...`). The leader learns the link state from the bridge's `notification_topic` instead of jobs' last wills. Open: replay order and duplicate rows, retained `$state` through the bridge, SD wear from persistence, broker credentials. | L | mosquitto config (CustoPiZer / `packaging/`), `config.ini` (`mqtt.broker_address`), the leader's online detection, `src/kiosk/` (connect locally) |

This is the heart of "accidental outages don't stop the bench" (L1 + L2), and nothing
about it needs v2 hardware. Prototype it opt-in on current workers to find the rough
edges early.

### v2

| # | Change | Size | Depends on |
| --- | --- | --- | --- |
| V1 | **One image, standalone first.** Every unit boots as leader+worker of a one-unit cluster. Joining switches it to worker (leader-only services off, broker becomes a bridge); leaving switches it back. | L (mostly CustoPiZer) | T9, T10, V2 |
| V3 | **Unboxing on the screen:** naming the unit (see "Still open"), Wi-Fi, then "standalone and ready". | M | V1 |
| V4 | **The leader's screen, cluster section:** units nearby (add), units in the cluster (remove, status tile), assign units to experiments, profiles. | M-L (frontend) | T5, T9 |
| V5 | **The worker's screen:** leave cluster, update this unit, edit `unit_config.ini`, version warning, leader-unreachable banner with full local control. | M (frontend) | T1, T7, T9, V2 |
| V6 | **History of a standalone that joins:** keep its database read-only on the unit, USB-exportable. | S | V1 |
| V7 | **Restore leader onto another unit;** workers re-find it by cluster id and re-point. | M | T3, T4, T5 |

### Suggested order

1. T0, T1, T2, T8: small, and they make today's clusters survive leader reboots.
2. T3: the biggest data-safety gain today.
3. T4, T5, T6, T7, T11: small groundwork with visible benefits.
4. T9, T10: the membership plumbing that v2 relies on.
5. V2 prototype, opt-in.
6. V1, V3-V7 with the v2 image.

## Sketch: the unit owns its model

**Why.** The model (for example `pioreactor_40ml` 1.5) is a fact about the hardware on
the bench, but today it lives only in the leader's `workers` table. Every model lookup
on a unit is a local one (`get_pioreactor_model()` with no argument, or the unit's own
name), and they sit on hot and safety paths: max temperature in `monitor.py` and the
temperature automations, max fill in `dosing_automation.py`, `actions/pump.py` and
`/unit_api` manual dosing, capacity in `bioreactor.py`, and the hardware layout in
`hardware.py`. Each goes env (`MODEL_NAME`/`MODEL_VERSION`), then a 30 s in-process
cache, then `GET /api/workers/<unit>` on the leader. A unit that can't reach the leader
can't resolve its own safety limits.

**Today's flow.**
- Set: `pio workers add -m -v`, `pio workers update-model`, the Inventory page and
  `MissingWorkerModelModal` all write the leader's `workers` row
  (`PUT /api/workers`, `PUT /api/workers/<unit>/model`). The leader then posts
  `/unit_api/hardware/check` to the unit, fire-and-forget.
- Read on the unit: `whoami._get_pioreactor_model_name_and_version`.
- Read by the leader and UI: the `workers` table (inventory, assignments, job env in
  `web/api.py` and `experiment_profile.py`, `GET /api/workers/<unit>/model`).
- Validated against the **leader's** model registry, though contrib model YAMLs live in
  each unit's `$DOT_PIOREACTOR/models/`.

**New flow.** The unit stores its model; the leader's columns become a mirror.

1. **Storage on the unit:** `local_persistent_storage("pioreactor_model")`, keys
   `model_name` and `model_version`. Same home as active calibrations: unit-owned state,
   survives reboots and leaving a cluster, included in `zipped_dot_pioreactor`.
   (Alternative: `[pioreactor] model_name/model_version` in `unit_config.ini`. Visible
   and editable in the config page, but it skips validation and the hardware check, and
   the same keys in the shared `config.ini` would be ambiguous.)
2. **Unit API** (`web/unit_api.py`):
   - `GET /unit_api/model`: name, version and the registry details; `404` when unset.
   - `PUT /unit_api/model {model_name, model_version}`: validates against **this
     unit's** registry, stores, runs the existing hardware check task, logs, and
     reports to the leader (step 4), best-effort.
3. **Lookups on the unit** (`whoami.py`): local store, then env, then the leader. Env
   drops below the local store so a stale mirror can't override the truth. The 30 s
   leader cache stays only for the fallback. If the store is empty and the leader
   answers, write the answer to the store (adopt it once): that's the migration, with
   no update script.
4. **The leader's mirror** (`web/api.py`):
   - `PUT /api/workers/<unit>/model` (UI and `pio workers update-model`) forwards to
     the unit's `PUT /unit_api/model` and updates the mirror only on success. As a Huey
     task answering `202`, so the single FastCGI process doesn't block on a worker. An
     unreachable unit is an error, not a silent mirror-only change.
   - A mirror-only route for units to report themselves, for example
     `PUT /api/workers/<unit>/reported_model` (no forward, so no loop).
   - The unit reports on every change and when its `monitor` starts (each boot), so
     changes made on the unit (its screen, a CLI) reach the leader.
5. **Adding a unit** (`cluster_management.add_worker`): with `-m -v`, set it on the
   unit (`PUT /unit_api/model`) after the join; without, read `GET /unit_api/model`
   into the mirror. For v2 units that already know their model, the "Add Pioreactor"
   dialog needs no model picker.
6. **Job env:** the leader can keep passing `MODEL_NAME`/`MODEL_VERSION` (old workers
   need it), but new units ignore it when their store is set. `/unit_api` manual
   dosing's safety check reads `whoami` instead of the env.
7. **A unit-local CLI:** `pio model get` / `pio model set NAME VERSION` (goes through the
   same code as `PUT /unit_api/model`), for units without a screen and for the screen
   itself.

**v1.x units (no screen).** The UI doesn't change; the leader's UI and CLI are how
these units learn their model, they just hand it to the unit now:

| Situation | What happens |
| --- | --- |
| Existing cluster updates | Each unit's store is empty. At its next `monitor` start (or first model lookup) it reads the leader's row and adopts it. Nothing for the user to do. |
| Add a new worker | The "Add new Pioreactor" dialog keeps its model picker (`POST /api/workers/setup` → `pio workers add -m -v`). After the join, the leader sets it on the unit (`PUT /unit_api/model`) and fills the mirror. |
| Added without a model (CLI without `-m`) | As today, `MissingWorkerModelModal` asks; its `PUT /api/workers/<unit>/model` now goes through to the unit. |
| Change the model later (e.g. a 20 ml unit rebuilt as 40 ml) | Inventory page, as today, through to the unit. If the unit is offline, the UI says so instead of only changing the leader's row. |
| Unit reflashed (store lost) | It adopts the leader's row again at boot: the mirror doubles as a backup. |
| Unit moved to another cluster | It keeps its store. The new leader's add dialog can prefill the picker from `GET /unit_api/model` (or the T5 mDNS record), and an explicit choice overrides it. |
| Someone at the unit over SSH | `pio model set NAME VERSION`, which reports to the leader. |

The only visible change on v1.x: changing a model needs the unit online.

**Mixed versions** (supported, see E4):
- New unit, old leader: the unit adopts the leader's answer once, then uses its store.
  A later change made in the old leader's UI doesn't reach it. Rare (the leader is
  usually updated first); warn in the release notes.
- Old unit, new leader: the forward to `PUT /unit_api/model` gets a `404`. Fall back to
  updating the mirror, as today.

**Tests:** `core/tests/test_whoami.py` (lookup order, adoption), unit API tests for
`GET`/`PUT /unit_api/model` (validation against the unit's registry), API tests for the
forward and the mirror-only route, and `cluster_management` add-worker paths.

**Later (v2):** the factory sets the model at provisioning (a bootfs file, alongside the
existing `models/` import, or the HAT's EEPROM), so a unit knows its model from first
boot.

## Still open

- **Naming at unboxing.** Today the hostname is set when flashing the card. Units that
  arrive pre-flashed and standalone all need unique names before they meet. Generate
  one from the serial number (for example `pio-3f2a`) and allow renaming on the screen?
  Renaming a unit later breaks its history's `pioreactor_unit` key.
- Which shared config a unit keeps when it leaves (lean in D4).
- What the leader shows for a unit that left while the leader couldn't reach it.
- A standalone unit's history on joining (lean in D2a / V6).

## Decisions

| Date | Question | Decision | Why |
| --- | --- | --- | --- |
| 2026-10-10 | B5: typical experiment size | Several Pioreactors | User's call. Implies the leader owns experiments, and makes L3 low value. |
| 2026-10-10 | Scope | Software rules can change for v2 | The screen ships with a v2 Pioreactor. |
| 2026-10-11 | G1: RTC | No battery-backed clock on v2 | User's call. Time stays network-sourced (A3). |
| 2026-10-11 | Moving units | Experiments are print jobs: a unit stays in its cluster during an experiment; moving it out is unsupported. Between experiments it's fine. Reassigning within the cluster is still allowed. | Aim for the 80% solution: the leader stays the authority during experiments. |
| 2026-10-11 | S4 | Out of scope | Follows from "experiments are print jobs". |
| 2026-10-11 | D1: unboxing | Standalone until joined: every unit boots as a one-unit cluster; joining another makes it a worker | User's call. |
| 2026-10-11 | "In an experiment" | While assigned | Matches today's assignment model and the experiment chip. |
| 2026-10-11 | A1: leader lost by accident mid-experiment | Full local control: banner, jobs keep running, data buffered, start/stop/adjust still work | User's call. |
| 2026-10-11 | B2: where experiments are set up | The leader's screen or the global UI; a laptop is optional | User's call. |
| 2026-10-11 | D2: joining | Added from the leader; nothing on the joining unit's screen | User's call. |
| 2026-10-11 | F3: leader screen scope | Assign + overview (no control of other units' jobs) | User's call. |
| 2026-10-11 | Worker web address | Redirects to the leader's global UI, focused on that unit | One global UI per cluster. |
| 2026-10-11 | D4: leaving | From either side: the leader, or the worker's own screen | E.g. taking a unit to another lab. |
| 2026-10-11 | D5: leader loss | Restore the latest backup onto another unit, which becomes the leader | The 80% answer. |
| 2026-10-11 | End of experiment on a unit's screen | Back to idle, no summary | History lives on the leader. |
| 2026-10-11 | F1: two control surfaces | No lock or notice; values update live over MQTT | Trusted lab, cheapest. |
| 2026-10-11 | G3: Pi | Pi 4 and Pi 5 only | v2 hardware. |
| 2026-10-11 | E1: config from the screen | A worker's screen edits its `unit_config.ini`; the leader's screen also edits the shared config | User's call. |
| 2026-10-11 | D4: what a leaving unit keeps | Calibrations and `unit_config.ini` | Shared config still open (lean: keep the last copy, re-pointed at itself). |
| 2026-10-11 | E3: plugins and updates | As today: cluster-wide or per unit, user's choice | No change. |
| 2026-10-11 | E4: updating from a unit's screen | Yes | User's call. |
| 2026-10-11 | E4: mixed versions | Supported, with a warning when a unit's version differs from the leader's | The cheap 80% answer. |
| 2026-10-11 | Model ownership | The unit stores its model; the leader's `workers` columns are a mirror | A hardware fact, on safety paths. Implement today (T0). |
| 2026-10-11 | Overall shape | Accepted ("The picture so far") | User confirmed. |
