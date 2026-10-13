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


def save_local_model(name: str, version: str, *, only_if_unset: bool = False) -> tuple[str, str]:
    if (name, version) not in get_registered_models():
        raise UnknownModelAssignedError(f"Unknown Pioreactor model {name} v{version}.")
    value = encode({"model_name": name, "model_version": version})
    with JobManager() as manager, local_persistent_storage("pioreactor_model") as storage:
        if only_if_unset:
            storage.set_if_absent("model", value)
        else:
            if manager.count_running_jobs(include_long_running_jobs=False):
                raise RuntimeError("Stop activities before changing the model.")
            storage["model"] = value
        saved = cast(dict[str, str], storage.getjson("model"))
    return saved["model_name"], saved["model_version"]


def report_model_to_leader(leader_address: str, name: str, version: str) -> bool:
    """Best-effort update of the leader's mirror of this unit's model."""
    # Lazy imports avoid the whoami/config initialization cycle.
    from pioreactor.mureq import HTTPException
    from pioreactor.pubsub import put_into
    from pioreactor.whoami import get_unit_name

    try:
        put_into(
            leader_address,
            f"/api/workers/{get_unit_name()}/reported_model",
            json={"model_name": name, "model_version": version},
            timeout=5,
        ).raise_for_status()
    except HTTPException:
        # Unreachable, or a worker the leader hasn't added yet. The leader's
        # GET /api/workers/<unit>/model asks the unit directly, so a stale mirror is tolerated.
        return False
    return True
