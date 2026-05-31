# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location(
    "generate_api_endpoint_docs",
    REPO_ROOT / "scripts/generate_api_endpoint_docs.py",
)
assert SPEC is not None and SPEC.loader is not None
generate_api_endpoint_docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_api_endpoint_docs)
parse_routes = generate_api_endpoint_docs.parse_routes
request_body_example = generate_api_endpoint_docs.request_body_example


def get_route(method: str, route: str) -> Any:
    routes = parse_routes(
        REPO_ROOT / "core/pioreactor/web/unit_api.py",
        "unit_api_bp",
        "/unit_api",
    )
    return next(candidate for candidate in routes if candidate.method == method and candidate.route == route)


def get_leader_route(method: str, route: str) -> Any:
    routes = parse_routes(
        REPO_ROOT / "core/pioreactor/web/api.py",
        "api_bp",
        "/api",
    )
    return next(candidate for candidate in routes if candidate.method == method and candidate.route == route)


def test_parse_routes_reads_required_struct_fields_from_decode_request_body() -> None:
    route = get_route("POST", "/unit_api/system/remove_file")

    assert route.required_body_keys == ("filepath",)
    assert route.optional_body_keys == ()
    assert route.body_type_names == ("structs.RemoveFileRequest",)


def test_parse_routes_reads_optional_struct_fields_from_decode_request_body() -> None:
    route = get_route("POST", "/unit_api/jobs/stop")

    assert route.required_body_keys == ()
    assert route.optional_body_keys == ("experiment", "job_id", "job_name", "job_source")
    assert route.body_type_names == ("structs.StopJobsRequest",)
    assert dict(route.body_key_types)["job_id"] == "integer"


def test_parse_routes_reads_inherited_optional_struct_fields() -> None:
    route = get_route("POST", "/unit_api/jobs/run/job_name/<job_name>")

    assert route.required_body_keys == ()
    assert route.optional_body_keys == ("args", "config_overrides", "env", "options")
    assert route.body_type_names == ("structs.ArgsOptionsEnvsConfigOverrides",)


def test_parse_routes_reads_existing_leader_decode_request_body_calls() -> None:
    route = get_leader_route("POST", "/api/experiment_profiles")

    assert route.required_body_keys == ("body", "filename")
    assert route.optional_body_keys == ()
    assert route.body_type_names == ("structs.CreateExperimentProfileRequest",)


def test_parse_routes_reads_new_leader_decode_request_body_calls() -> None:
    route = get_leader_route("POST", "/api/system/update_from_archive")

    assert route.required_body_keys == ("release_archive_location", "units")
    assert route.optional_body_keys == ()
    assert route.body_type_names == ("structs.UpdateAppFromReleaseArchiveRequest",)


def test_parse_routes_reads_optional_leader_decode_request_body_fields() -> None:
    route = get_leader_route("POST", "/api/system/update_next_version")

    assert route.required_body_keys == ()
    assert route.optional_body_keys == ("units",)
    assert route.body_type_names == ("structs.UpdateAppRequest",)


def test_parse_routes_reads_app_owned_experiment_mutation_body_fields() -> None:
    route = get_leader_route("POST", "/api/experiments")

    assert route.required_body_keys == ("experiment",)
    assert route.optional_body_keys == (
        "created_at",
        "delta_hours",
        "description",
        "mediaUsed",
        "organismUsed",
        "tags",
        "worker_count",
    )
    assert route.body_type_names == ("structs.CreateExperimentRequest",)
    assert dict(route.body_key_types)["tags"] == "array"


def test_create_experiment_docs_hide_compatibility_only_fields() -> None:
    route = get_leader_route("POST", "/api/experiments")

    assert request_body_example(route) == {
        "experiment": "testing_experiment",
        "description": "Experiment notes.",
        "mediaUsed": "LB",
        "organismUsed": "E. coli",
        "tags": ["screening"],
    }


def test_parse_routes_reads_experiment_patch_body_fields_as_optional() -> None:
    route = get_leader_route("PATCH", "/api/experiments/<experiment>")

    assert route.required_body_keys == ()
    assert route.optional_body_keys == ("description", "tags")
    assert route.body_type_names == ("structs.UpdateExperimentRequest",)


def test_parse_routes_reads_app_owned_worker_mutation_body_fields() -> None:
    route = get_leader_route("PUT", "/api/workers/<pioreactor_unit>/model")

    assert route.required_body_keys == ("model_name", "model_version")
    assert route.optional_body_keys == ()
    assert route.body_type_names == ("structs.ChangeWorkerModelRequest",)


def test_parse_routes_reads_calibration_session_proxy_body_fields() -> None:
    route = get_leader_route("POST", "/api/workers/<pioreactor_unit>/calibrations/sessions")

    assert route.required_body_keys == ("protocol_name", "target_device")
    assert route.optional_body_keys == ()
    assert route.body_type_names == ("structs.StartCalibrationSessionRequest",)


def test_parse_routes_reads_unit_specific_config_body_fields() -> None:
    route = get_leader_route("PATCH", "/api/config/units/<pioreactor_unit>/specific")

    assert route.required_body_keys == ("code",)
    assert route.optional_body_keys == ()
    assert route.body_type_names == ("structs.CodePatch",)


def test_parse_routes_reads_command_envelope_body_fields() -> None:
    route = get_leader_route("POST", "/api/units/<pioreactor_unit>/plugins/install")

    assert route.required_body_keys == ()
    assert route.optional_body_keys == ("args", "env", "options")
    assert route.body_type_names == ("structs.ArgsOptionsEnvs",)
