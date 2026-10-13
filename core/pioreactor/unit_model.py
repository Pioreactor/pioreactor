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


def adopt_model_from_leader() -> tuple[str, str] | None:
    # Lazy import avoids the whoami/config initialization cycle.
    from pioreactor import whoami

    if (local := get_local_model()) is not None:
        return local
    name, version = whoami._get_pioreactor_model_name_and_version_from_leader(whoami.get_unit_name())
    if name is None or version is None:
        return None
    return save_local_model(name, version, only_if_unset=True)
