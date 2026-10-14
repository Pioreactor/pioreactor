# -*- coding: utf-8 -*-
"""The local model assignment is one atomic, validated persistent value."""
from typing import cast

from msgspec.json import encode
from pioreactor.exc import UnknownModelAssignedError
from pioreactor.models import get_registered_models
from pioreactor.utils.job_manager import JobManager
from pioreactor.utils.sqlite_cache import local_persistent_storage


def get_local_model() -> tuple[str, str] | None:
    with local_persistent_storage("pioreactor_model") as storage:
        value = storage.getjson("model")
    if value is None:
        return None
    model = cast(dict[str, str], value)
    return model["model_name"], model["model_version"]


def _encode_model(model_name: str, model_version: str) -> bytes:
    if (model_name, model_version) not in get_registered_models():
        raise UnknownModelAssignedError(f"Unknown Pioreactor model {model_name} v{model_version}.")
    return encode({"model_name": model_name, "model_version": model_version})


def save_local_model(model_name: str, model_version: str) -> None:
    value = _encode_model(model_name, model_version)
    with JobManager() as manager:
        if manager.count_running_jobs(include_long_running_jobs=False):
            raise RuntimeError("Stop activities before changing the model.")
    with local_persistent_storage("pioreactor_model") as storage:
        storage["model"] = value


def adopt_leader_model() -> tuple[str, str] | None:
    """
    Save the leader's record of this unit's model, if this unit has none. Units upgraded from
    before they stored their own model run this once (see `pio model adopt`).
    """
    # Lazy imports avoid the whoami/config initialization cycle.
    from pioreactor.mureq import HTTPErrorStatus
    from pioreactor.pubsub import get_from_leader
    from pioreactor.whoami import get_unit_name

    if (local := get_local_model()) is not None:
        return local

    try:
        response = get_from_leader(f"/api/workers/{get_unit_name()}")
        response.raise_for_status()
    except HTTPErrorStatus as e:
        if e.status_code == 404:
            # Not in the leader's inventory, e.g. a leader that isn't also a worker.
            return None
        raise

    data = response.json()
    if data["model_name"] is None or data["model_version"] is None:
        return None
    # No running-activities check: the model those activities use doesn't change.
    value = _encode_model(data["model_name"], data["model_version"])
    with local_persistent_storage("pioreactor_model") as storage:
        storage.set_if_absent("model", value)
    return get_local_model()


def check_model_hardware(model_name: str, model_version: str) -> dict[str, str]:
    """Check this unit's HAT has the model's hardware, and log the outcome."""
    # Lazy imports: hardware detection is slow to import, and whoami imports this module.
    from pioreactor.hardware import check_model_hardware_compatibility
    from pioreactor.logging import create_logger
    from pioreactor.whoami import get_unit_name
    from pioreactor.whoami import UNIVERSAL_EXPERIMENT

    logger = create_logger("model", experiment=UNIVERSAL_EXPERIMENT)
    unit = get_unit_name()
    result = check_model_hardware_compatibility(model_name, model_version)

    if result["status"] == "skipped":
        logger.debug(f"Hardware check skipped on `{unit}`: {result['reason']}")
    elif result["status"] == "warning":
        logger.warning(f"Hardware check failed on `{unit}`: {result['reason']}")
        result = {**result, "reason": result["reason"].split(": ", 1)[-1]}
    elif result["status"] == "ok":
        logger.notice(f"Correct hardware found for {model_name} {model_version} on `{unit}`.")

    return result


def report_model_to_leader(leader_address: str, model_name: str, model_version: str) -> bool:
    """Best-effort update of the leader's mirror of this unit's model."""
    # Lazy imports avoid the whoami/config initialization cycle.
    from pioreactor.mureq import HTTPException
    from pioreactor.pubsub import put_into
    from pioreactor.whoami import get_unit_name

    try:
        put_into(
            leader_address,
            f"/api/workers/{get_unit_name()}/reported_model",
            json={"model_name": model_name, "model_version": model_version},
            timeout=5,
        ).raise_for_status()
    except HTTPException:
        # Unreachable, or a worker the leader hasn't added yet. The leader's
        # GET /api/workers/<unit>/model asks the unit directly, so a stale mirror is tolerated.
        return False
    return True
