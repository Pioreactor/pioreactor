# -*- coding: utf-8 -*-
"""Whether this unit is in service. The unit owns it; the leader's `workers.is_active` mirrors it."""
from pioreactor.utils.job_manager import JobManager
from pioreactor.utils.sqlite_cache import local_persistent_storage


def is_locally_active() -> bool:
    # A unit boots for the first time active.
    with local_persistent_storage("unit_active") as storage:
        return storage.getboolean("is_active", fallback=True)


def save_local_active(is_active: bool, stop_activities: bool = True) -> None:
    # Save first, so no activity starts between stopping them and saving.
    with local_persistent_storage("unit_active") as storage:
        storage["is_active"] = int(is_active)
    if not is_active and stop_activities:
        with JobManager() as manager:
            manager.kill_jobs(all_jobs=True)


def adopt_leader_active() -> bool:
    """
    Save the leader's record of whether this unit is active. Run once by the update that moved
    ownership from the leader to each unit (see `pio active adopt`): until then, the leader's
    record was the truth.
    """
    # Lazy imports avoid the whoami/config initialization cycle.
    from pioreactor.mureq import HTTPErrorStatus
    from pioreactor.pubsub import get_from_leader
    from pioreactor.whoami import get_unit_name

    try:
        response = get_from_leader(f"/api/workers/{get_unit_name()}")
        response.raise_for_status()
    except HTTPErrorStatus as e:
        if e.status_code == 404:
            # Not in the leader's inventory, e.g. a leader that isn't also a worker.
            return is_locally_active()
        raise

    # No stopping activities: an inactive unit had none, since the leader stopped them.
    is_active = bool(response.json()["is_active"])
    save_local_active(is_active, stop_activities=False)
    return is_active


def report_active_to_leader(leader_address: str, is_active: bool) -> bool:
    """Best-effort update of the leader's mirror of whether this unit is active."""
    # Lazy imports avoid the whoami/config initialization cycle.
    from pioreactor.mureq import HTTPException
    from pioreactor.pubsub import put_into
    from pioreactor.whoami import get_unit_name

    try:
        put_into(
            leader_address,
            f"/api/workers/{get_unit_name()}/reported_active",
            json={"is_active": int(is_active)},
            timeout=5,
        ).raise_for_status()
    except HTTPException:
        # Unreachable, or a worker the leader hasn't added yet. A stale mirror fails safe: the
        # leader may send work that this unit refuses, or skip a unit that's in service.
        return False
    return True
