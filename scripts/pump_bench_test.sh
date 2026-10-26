#!/usr/bin/env bash
# Upload this single file. Run as pioreactor, interactively, on xr1.local.
# Requires the refactored package to already be installed. Does not deploy code.
set -euo pipefail
if [[ ${1:-} == --help ]]; then
    echo 'Usage: bash pump_bench_test.sh [media|alt_media|waste]'
    echo 'Default: waste. Interactive real-hardware tests; use water routed outside the reactor.'
    exit 0
fi
pump=${1:-waste}
case "$pump" in media|alt_media|waste) ;; *) echo 'Choose media, alt_media, or waste.' >&2; exit 2 ;; esac
[[ -t 0 ]] || { echo 'An interactive terminal is required.' >&2; exit 1; }
[[ $(hostname -s) == xr1 ]] || { echo 'This script is restricted to xr1.' >&2; exit 1; }
[[ $(id -u) != 0 ]] || { echo 'Run as pioreactor, without sudo.' >&2; exit 1; }
python_bin=${PIO_VENV:-/opt/pioreactor/venv}/bin/python
[[ -x "$python_bin" ]] || { echo "Missing interpreter: $python_bin" >&2; exit 1; }
results_dir=$(mktemp -d "$HOME/pump-bench-$(date +%Y%m%d-%H%M%S)-XXXXXX")
exec > >(tee -a "$results_dir/session.log") 2>&1
printf 'Results: %s\n' "$results_dir"
cat > "$results_dir/probe.py" <<'PYTHON'
import hashlib
import inspect
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from pioreactor.actions import pump as pumps
from pioreactor.actions.pump_execution import PumpRun
from pioreactor.background_jobs.dosing_automation import DosingAutomationJob
from pioreactor.exc import PWMLockedError
from pioreactor.pubsub import publish
from pioreactor.utils import is_pio_job_running, local_intermittent_storage
from pioreactor.whoami import get_assigned_experiment_name, get_unit_name, is_testing_env

DEVICE = sys.argv[1]
UNIT = get_unit_name()
EXPERIMENT = get_assigned_experiment_name(UNIT)
PIN = pumps._get_pin(DEVICE + "_pump")
ACTION = {"media": pumps.add_media, "alt_media": pumps.add_alt_media, "waste": pumps.remove_waste}[DEVICE]
DURATION = 4.0  # Every operation is finite, including interrupted operations.


def snapshot() -> None:
    with local_intermittent_storage("pwm_locks") as locks:
        owner = locks.get(PIN)
    with local_intermittent_storage("pwm_dc") as cache:
        duty = cache.get(PIN, 0)
    print(f"Postcondition: pin={PIN}, lock={owner!r}, cached_dc={duty}", flush=True)
    if owner is not None or duty != 0:
        raise RuntimeError("Pin ownership/cache did not clear. Do not purge it; investigate.")


def new_pump(cancel: threading.Event | None = None) -> pumps.PWMPump:
    return pumps.PWMPump(
        UNIT,
        EXPERIMENT,
        PIN,
        pumps._get_calibration(DEVICE + "_pump"),
        cancel_events=() if cancel is None else (cancel,),
    )


def low_level(case: str) -> None:
    cancel = threading.Event()
    with new_pump(cancel) as pump:
        started = time.monotonic()
        seconds = 0.4 if case == "restart" else 2.0
        pump.by_duration(seconds, block=False)
        print(f"OUTPUT STARTED: {seconds}s maximum requested duration", flush=True)
        if case == "cancel":
            time.sleep(0.6)
            cancel.set()
        elif case == "busy":
            try:
                with new_pump():
                    raise RuntimeError("Second owner unexpectedly acquired the pin")
            except PWMLockedError:
                print("PASS: competing owner rejected", flush=True)
        elif case == "telemetry":
            original_publish = pump.pwm.pub_client.publish

            def delayed_publish(*args: object, **kwargs: object) -> object:
                print("Telemetry deliberately blocked for 3s; output should stop at 2s.", flush=True)
                time.sleep(3)
                return original_publish(*args, **kwargs)

            pump.pwm.pub_client.publish = delayed_publish
            try:
                pump.publish_duty_cycles()
            finally:
                pump.pwm.pub_client.publish = original_publish
        if not pump.wait(5):
            raise RuntimeError("Worker did not finish")
        pump.stop()
        print(
            f"Worker elapsed={pump.elapsed:.3f}s; wall={time.monotonic()-started:.3f}s; completed={pump.completed}",
            flush=True,
        )
        expected = 0.6 if case == "cancel" else seconds
        if abs(pump.elapsed - expected) > 0.4:
            raise RuntimeError("Worker duration outside 0.4s bench tolerance")
        if pump.completed != (case != "cancel"):
            raise RuntimeError("Unexpected completion state")


def lifecycle(case: str) -> None:
    family, stop = case.split(":")
    job_name = (
        {"media": "add_media", "alt_media": "add_alt_media", "waste": "remove_waste"}[DEVICE]
        if family == "standalone"
        else "dosing_automation"
    )
    control_sent = threading.Event()
    control_errors: list[str] = []

    def interrupt() -> None:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            with local_intermittent_storage("pwm_dc") as cache:
                active = cache.get(PIN, 0) > 0
            if active:
                time.sleep(0.6)
                print(f"CONTROL: {stop} -> {job_name}", flush=True)
                control_sent.set()
                if stop in ("SIGINT", "SIGTERM"):
                    os.kill(os.getpid(), getattr(signal, stop))
                else:
                    publish(f"pioreactor/{UNIT}/{EXPERIMENT}/{job_name}/$state/set", stop, retain=False)
                return
            time.sleep(0.02)
        control_errors.append("No active PWM telemetry observed; control was not sent")

    class BenchAutomation(DosingAutomationJob):
        automation_name = "pump_bench"

        def execute(self) -> None:
            moved = ACTION(
                unit=self.unit,
                experiment=self.experiment,
                duration=DURATION,
                mqtt_client=self.pub_client,
                logger=self.logger,
                cancel_event=self._stop_pumping_event,
            )
            print(f"Action returned estimated volume: {moved:.5f}mL", flush=True)

    controller = threading.Thread(target=interrupt, daemon=True)
    start = time.monotonic()
    if family == "standalone":
        controller.start()
        try:
            ACTION(unit=UNIT, experiment=EXPERIMENT, duration=DURATION)
        except KeyboardInterrupt:
            pass
    else:
        with BenchAutomation(
            unit=UNIT,
            experiment=EXPERIMENT,
            current_volume_ml=10,
            efflux_tube_volume_ml=10,
            alt_media_fraction=0,
        ) as job:
            controller.start()
            try:
                if family == "event":
                    job.trigger_run_once_from_event()
                else:
                    job._set_periodic_timer(1, skip_first_run=False, run_after_seconds=0)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if control_sent.is_set() and job.state in (job.SLEEPING, job.DISCONNECTED):
                        break
                    time.sleep(0.02)
                else:
                    raise RuntimeError("Automation did not enter requested state")
            except KeyboardInterrupt:
                pass
    controller.join(timeout=9)
    elapsed = time.monotonic() - start
    print(f"Lifecycle wall time including startup/cleanup: {elapsed:.3f}s", flush=True)
    if not control_sent.is_set() or control_errors or controller.is_alive():
        raise RuntimeError(f"Control failed: {control_errors}")
    if elapsed >= DURATION:
        raise RuntimeError("Shutdown took >= full dose duration; investigate timing/control delivery")


def run_child(case: str) -> None:
    child = subprocess.Popen([sys.executable, "-u", __file__, DEVICE, case])
    try:
        code = child.wait(timeout=20)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        child.terminate()
        print("ABORT: inspect output now; disconnect pump power if still running.", flush=True)
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"Child PID {child.pid} remains alive; no SIGKILL or lock purge was attempted.")
        raise RuntimeError("Test interrupted or timed out") from None
    if code:
        raise RuntimeError(f"Case {case} exited {code}; stopping for investigation")
    snapshot()


def main() -> None:
    if is_testing_env():
        raise RuntimeError("TESTING=1 would use mock hardware; refusing")
    if len(sys.argv) == 3:
        case = sys.argv[2]
        if ":" in case:
            lifecycle(case)
        else:
            low_level(case)
        snapshot()
        return

    print(f"Unit={UNIT}, experiment={EXPERIMENT}, pump={DEVICE}, GPIO={PIN}")
    print(f"Python={sys.executable}; data root={os.environ.get('DOT_PIOREACTOR')}")
    for source in (pumps, sys.modules[PumpRun.__module__]):
        path = Path(inspect.getfile(source))
        print(f"Installed source: {path}; sha256={hashlib.sha256(path.read_bytes()).hexdigest()}")
    if "cancel_event" not in inspect.signature(ACTION).parameters or not hasattr(pumps.PWMPump, "wait"):
        raise RuntimeError("Expected refactored API is not installed")
    jobs = [
        "dosing_automation",
        "add_media",
        "add_alt_media",
        "remove_waste",
        "circulate_media",
        "circulate_alt_media",
    ]
    if any(is_pio_job_running(jobs)):
        raise RuntimeError("Existing liquid-handling job detected. Stop it yourself before testing.")
    snapshot()
    print("Use a disposable assigned experiment: high-level cases publish REAL dosing events/settings.")
    print("Route the selected pump from water into a separate catch vessel, outside the reactor.")
    print("Check correct tubing/direction, ample water/catch capacity, and access to pump power.")
    print("Each case requests at most 4s of pumping; restart checks request 0.4s.")
    print(
        "If output stays on unexpectedly: disconnect pump power. Software timeout is not an independent cutoff."
    )
    if input("Type BENCH to confirm this setup (anything else exits): ").strip() != "BENCH":
        return
    cases = ["timed", "cancel", "busy", "telemetry"]
    cases += [
        f"{family}:{stop}"
        for family in ("standalone", "event", "periodic")
        for stop in ("SIGINT", "SIGTERM", "disconnected")
    ]
    cases += ["event:sleeping"]
    for case in cases:
        print(f"\nCASE {case}: expect only selected pump to run, then stop completely.")
        answer = input("Enter=run, s=skip, q=quit: ").strip().lower()
        if answer == "q":
            break
        if answer == "s":
            print(f"SKIP {case}")
            continue
        if answer:
            raise RuntimeError("Unrecognized choice; stopping")
        run_child(case)
        observation = input("Physical result: type PASS followed by notes, or describe the failure: ")
        print(f"OBSERVATION {case}: {observation}", flush=True)
        if observation.split()[:1] != ["PASS"]:
            raise RuntimeError("Physical result not confirmed; stopping")
        print("Check same-pin reuse: next confirmation runs a 0.4s pulse.")
        if input("Enter=run restart check; anything else ends session: "):
            break
        run_child("restart")
        observation = input("Did the restart pulse run and stop? Type PASS plus notes: ")
        print(f"OBSERVATION {case} restart: {observation}", flush=True)
        if observation.split()[:1] != ["PASS"]:
            raise RuntimeError("Restart not physically confirmed")
    print("Session finished. Software state checks and operator observations are separate evidence.")


if __name__ == "__main__":
    main()
PYTHON
"$python_bin" -u "$results_dir/probe.py" "$pump"
