#!/usr/bin/env bash

# Pioreactor Production Smoke Test
#
# Purpose: Run the quick, non-destructive checks from AGENT_TESTING.md
#          on a Raspberry Pi Pioreactor. Continues on failure, reports errors in red.
#
# Usage (on the Pi):
#   chmod +x ./pioreactor_agent_smoke_test.sh
#   ./pioreactor_agent_smoke_test.sh
#
# Notes:
# - Run as the `pioreactor` user (not root).
# - Assumes official image with `pio` CLI installed.
# - Requires `curl`. `jq` is optional for prettier JSON checks.
# - Worker packaging checks use the leader's SSH key to workers when available.

set -uo pipefail

FAILURE_COUNT=0
VERIFIED_IDLE_BEFORE=false
HAS_JQ=false
HAS_SYSTEMCTL=false
AVAILABLE_WORKER_NAME=""
AVAILABLE_WORKER_ADDRESS=""
AVAILABLE_WORKER_IS_ACTIVE=""
AVAILABLE_WORKER_MODEL_NAME=""
AVAILABLE_WORKER_MODEL_VERSION=""

declare -a TEST_SEQUENCE=(
  check_versions
  check_configuration_files
  check_config_api_endpoints
  check_services
  check_runtime_packaging
  check_ui_static_assets
  check_kiosk_route
  check_mqtt_logging
  check_monitor_job
  check_database_access
  check_worker_model_metadata
  check_unit_model_contract
  check_unit_api_core
  check_registered_target_validation
  check_mutation_target_guard
  check_cross_site_write_protection
  check_usb_status_surface
  check_descriptor_endpoints
  check_calibration_session_tasks
  check_camera_contract
  check_unit_api_job_history
  check_blink
  check_pio_run_latency
  check_pio_logs_cli
  check_pio_usb_cli
  check_update_cli_contract
  check_leader_api
  check_time_series_endpoints
  check_experiment_cli
  check_stirring_job
  check_experiment_scoping
  check_experiment_profiles
  check_experiment_profile_validation
  check_exportable_datasets_listing
  check_exportable_dataset_preview_validation
  check_export_datasets_endpoint
  check_dropin_plugin_discovery
  check_calibration_discovery
  check_storage_path_validation
  check_broadcast_endpoints
  check_thermostat_job
  check_pump_actions
  check_bioreactor_topic_payloads
  check_plugin_install_cycle
  check_pios_cli
  check_pios_cp_target_help
  check_pios_sync_configs
  check_available_worker_cluster_branch
  check_numpy_installation
)

declare -a SELECTED_TESTS=()

JOB_SYNC_DELAY=2.0

RED='\033[0;31m'
NC='\033[0m'

log() {
  printf "[%s] %s\n" "$1" "$2"
}

info() {
  log info "$1"
}

ok() {
  log ok "$1"
}

fail() {
  printf "${RED}[fail] %s${NC}\n" "$1"
  FAILURE_COUNT=$((FAILURE_COUNT + 1))
}

warn() {
  log warn "$1"
}

usage() {
  cat <<'EOF'
Usage: ./pioreactor_agent_smoke_test.sh [-t test_name]...

Run the Pioreactor smoke tests. Without options, all tests run in sequence.

Options:
  -t test_name  Run only the specified test function (repeatable)
  -h            Show this help message and exit
EOF
}

parse_args() {
  OPTIND=1
  while getopts ":t:h" opt; do
    case "$opt" in
      t)
        SELECTED_TESTS+=("$OPTARG")
        ;;
      h)
        usage
        exit 0
        ;;
      :)
        printf "Option -%s requires an argument\n" "$OPTARG" >&2
        usage >&2
        exit 1
        ;;
      \?)
        printf "Unknown option: -%s\n" "$OPTARG" >&2
        usage >&2
        exit 1
        ;;
    esac
  done
}

require_cmd() {
  local missing=()
  for cmd in "$@"; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      missing+=("$cmd")
    fi
  done

  if ((${#missing[@]} > 0)); then
    fail "Missing required command(s): ${missing[*]}"
  fi
}

ensure_not_root() {
  if [[ -n "${SUDO_USER:-}" || -n "${SUDO_UID:-}" ]]; then
    printf "${RED}[fail] Do not run with sudo. Switch to the 'pioreactor' user and run directly.${NC}\n"
    exit 1
  fi

  if [[ "$EUID" -eq 0 ]]; then
    printf "${RED}[fail] Do not run as root. Switch to the 'pioreactor' user and run directly.${NC}\n"
    exit 1
  fi

  local current_user
  current_user="$(id -un)"
  if [[ "$current_user" != "pioreactor" ]]; then
    fail "User is '$current_user'; recommended to run as 'pioreactor'."
  fi
}

enter_pioreactor_home() {
  if [[ -d "/home/pioreactor" ]]; then
    if ! cd /home/pioreactor; then
      fail "Unable to cd to /home/pioreactor"
    fi
  fi
}

detect_optional_tools() {
  if command -v jq >/dev/null 2>&1; then
    HAS_JQ=true
  else
    warn "jq not found; JSON validation will be basic"
  fi

  if command -v systemctl >/dev/null 2>&1; then
    HAS_SYSTEMCTL=true
  fi
}

http_json_ok() {
  # Usage: http_json_ok URL [jq_filter]
  local url="$1"
  local jq_filter="${2:-}"
  local response

  if ! response="$(curl -fsS "$url")"; then
    return 1
  fi

  if [[ "$HAS_JQ" == true ]]; then
    if [[ -n "$jq_filter" ]]; then
      echo "$response" | jq -e "$jq_filter" >/dev/null
    else
      echo "$response" | jq . >/dev/null
    fi
  else
    if [[ -n "$jq_filter" ]]; then
      warn "Skipping JSON filter '$jq_filter' for $url (jq not installed)"
    fi
    [[ -n "$response" ]]
  fi
}

run_step() {
  # Usage: run_step "Description" command [args...]
  local description="$1"
  shift

  info "$description"
  if "$@"; then
    ok "$description"
    return 0
  fi

  fail "$description"
  return 1
}

curl_check() {
  # Wrapper used with run_step for readability.
  local url="$1"
  local jq_filter="${2:-}"
  http_json_ok "$url" "$jq_filter"
}

curl_ok() {
  local url="$1"
  curl -fsS "$url" >/dev/null
}

http_status_is() {
  local expected_status="$1"
  local url="$2"
  shift 2

  local status
  status="$(curl -sS -o /dev/null -w "%{http_code}" "$@" "$url")"
  [[ "$status" == "$expected_status" ]]
}

http_header_value() {
  # Usage: http_header_value HEADER_NAME URL [curl args...]
  # Prints the response header's value, or nothing when the header is absent.
  local header_name="${1,,}"
  local url="$2"
  shift 2

  curl -sS -D - -o /dev/null "$@" "$url" | tr -d '\r' | \
    awk -v name="$header_name" '
      {
        split($0, parts, ":")
        if (tolower(parts[1]) == name) {
          value = $0
          sub(/^[^:]*:[[:space:]]*/, "", value)
        }
      }
      END { print value }
    '
}

mqtt_read_one() {
  # Usage: mqtt_read_one TOPIC [TIMEOUT_SECONDS]
  # Prints the first payload on TOPIC (for retained topics, the retained message).
  local topic="$1"
  local timeout_seconds="${2:-5}"
  local host port username password

  host="$(pio config get mqtt broker_address 2>/dev/null | tr -d '[:space:]')"
  port="$(pio config get mqtt broker_port 2>/dev/null | tr -d '[:space:]')"
  username="$(pio config get mqtt username 2>/dev/null | tr -d '[:space:]')"
  password="$(pio config get mqtt password 2>/dev/null | tr -d '[:space:]')"

  mosquitto_sub \
    -h "${host:-localhost}" \
    -p "${port:-1883}" \
    -u "${username:-pioreactor}" \
    -P "${password:-raspberry}" \
    -t "$topic" \
    -C 1 \
    -W "$timeout_seconds"
}

mqtt_checks_available() {
  if [[ "$HAS_JQ" != true ]]; then
    warn "jq not installed; skipping MQTT payload checks"
    return 1
  fi

  if ! command -v mosquitto_sub >/dev/null 2>&1; then
    fail "mosquitto_sub missing; mosquitto-clients should be installed on every unit"
    return 1
  fi

  if [[ "$(pio config get mqtt use_tls 2>/dev/null | tr -d '[:space:]')" == "1" ]]; then
    warn "MQTT uses TLS; skipping MQTT payload checks"
    return 1
  fi
}

get_assigned_experiment_via_api() {
  # Prints the experiment assigned to a unit, or nothing when it is unassigned.
  local unit="$1"
  local response_file status
  response_file="$(mktemp)"

  status="$(curl -sS -o "$response_file" -w "%{http_code}" "http://localhost/api/workers/$unit/experiment")"
  case "$status" in
    200)
      jq -r '.experiment // empty' "$response_file"
      ;;
    404)
      ;;
    *)
      rm -f "$response_file"
      return 1
      ;;
  esac
  rm -f "$response_file"
}

uri_encode() {
  jq -rn --arg value "$1" '$value | @uri'
}

no_short_lived_jobs_running() {
  # Model changes are refused while activities (anything except long-running services) run.
  local jobs_json
  jobs_json="$(fetch_running_jobs)" || return 1
  jq -e 'all(.[]; (.is_long_running_job // 0) == 1)' <<< "$jobs_json" >/dev/null
}

fetch_running_jobs() {
  curl -fsS http://localhost/unit_api/jobs/running
}

jobs_contain() {
  local jobs_json="$1"
  local jq_query="$2"

  if [[ "$HAS_JQ" == true ]]; then
    echo "$jobs_json" | jq -e "$jq_query" >/dev/null
  else
    warn "Cannot evaluate jq expression '$jq_query' (jq not installed)"
    return 1
  fi
}

read_pwm_duty_cycle() {
  local raw
  if ! raw="$(pio cache view pwm_dc)"; then
    return 1
  fi

  if [[ "$HAS_JQ" == true && ( "$raw" == \{* || "$raw" == \[* ) ]]; then
    local value
    value="$(jq -r '."1" // ."17" // (.. | numbers)' <<<"$raw" | head -n 1)"
    if [[ -n "$value" && "$value" != "null" ]]; then
      printf '%s\n' "$value"
      return 0
    fi
  fi

  local value
  value="$(printf '%s\n' "$raw" | awk -F'=' 'NF >= 2 {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $1); gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); if ($1=="1" || $1=="17") {print $2; exit}}')"

  if [[ -z "$value" ]]; then
    value="$(printf '%s\n' "$raw" | awk '{for(i=1;i<=NF;i++){if($i ~ /^[0-9]+(\.[0-9]+)?$/){print $i; exit}}}')"
  fi

  if [[ -n "$value" ]]; then
    printf '%s\n' "$value"
    return 0
  fi

  return 1
}

is_positive_number() {
  local value="$1"
  awk -v n="$value" 'BEGIN {exit (n+0 > 0 ? 0 : 1)}'
}

python3_available() {
  command -v python3 >/dev/null 2>&1
}

json_file_for_code_patch() {
  # Usage: json_file_for_code_patch CODE_FILE JSON_FILE
  local code_file="$1"
  local json_file="$2"

  python3 - "$code_file" > "$json_file" <<'PY'
import json
import pathlib
import sys

print(json.dumps({"code": pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")}))
PY
}

worker_base_url() {
  local address="$1"

  case "$address" in
    http://*|https://*)
      printf '%s\n' "$address"
      ;;
    *)
      printf 'http://%s\n' "$address"
      ;;
  esac
}

select_available_worker() {
  if [[ -n "$AVAILABLE_WORKER_NAME" ]]; then
    return 0
  fi

  if ! python3_available; then
    warn "python3 not available; skipping worker-cluster branch"
    return 1
  fi

  local workers_json hostname
  hostname="$(hostname)"
  if ! workers_json="$(curl -fsS http://localhost/api/workers)"; then
    warn "Unable to fetch worker inventory; skipping worker-cluster branch"
    return 1
  fi

  local candidates
  if ! candidates="$(WORKERS_JSON="$workers_json" python3 - "$hostname" <<'PY'
import json
import os
import sys

hostname = sys.argv[1]
workers = json.loads(os.environ["WORKERS_JSON"])

for worker in workers:
    unit = str(worker.get("pioreactor_unit") or "")
    if not unit or unit == hostname:
        continue
    if not bool(worker.get("is_active")):
        continue

    address = str(worker.get("ipv4_address") or worker.get("address") or f"{unit}.local")
    model_name = str(worker.get("model_name") or "")
    model_version = str(worker.get("model_version") or "")
    print("|".join([unit, address, "1", model_name, model_version]))
PY
)"; then
    warn "Unable to parse worker inventory; skipping worker-cluster branch"
    return 1
  fi

  local candidate unit address is_active model_name model_version base_url
  while IFS= read -r candidate; do
    [[ -n "$candidate" ]] || continue
    IFS='|' read -r unit address is_active model_name model_version <<< "$candidate"
    base_url="$(worker_base_url "$address")"
    if curl -fsS --max-time 5 "$base_url/unit_api/system/utc_clock" >/dev/null; then
      AVAILABLE_WORKER_NAME="$unit"
      AVAILABLE_WORKER_ADDRESS="$address"
      AVAILABLE_WORKER_IS_ACTIVE="$is_active"
      AVAILABLE_WORKER_MODEL_NAME="$model_name"
      AVAILABLE_WORKER_MODEL_VERSION="$model_version"
      return 0
    fi
  done <<< "$candidates"

  warn "No active non-leader worker responded to /unit_api/system/utc_clock; skipping worker-cluster branch"
  return 1
}

worker_inventory_contains() {
  local worker="$1"
  local workers_json

  if ! workers_json="$(curl -fsS http://localhost/api/workers)"; then
    return 1
  fi

  WORKERS_JSON="$workers_json" python3 - "$worker" <<'PY'
import json
import os
import sys

target = sys.argv[1]
workers = json.loads(os.environ["WORKERS_JSON"])
sys.exit(0 if any(worker.get("pioreactor_unit") == target for worker in workers) else 1)
PY
}

refresh_available_worker_address_from_inventory() {
  local worker="$1"
  local workers_json address

  if ! workers_json="$(curl -fsS http://localhost/api/workers)"; then
    return 1
  fi

  if ! address="$(WORKERS_JSON="$workers_json" python3 - "$worker" <<'PY'
import json
import os
import sys

target = sys.argv[1]
workers = json.loads(os.environ["WORKERS_JSON"])
for worker in workers:
    if worker.get("pioreactor_unit") == target:
        print(worker.get("ipv4_address") or worker.get("address") or "")
        raise SystemExit(0)
raise SystemExit(1)
PY
)"; then
    return 1
  fi

  if [[ -n "$address" ]]; then
    AVAILABLE_WORKER_ADDRESS="$address"
  fi
}

wait_for_available_worker_api() {
  local worker="$1"
  local base_url

  info "Waiting for worker $worker API to become available"
  for _ in {1..60}; do
    refresh_available_worker_address_from_inventory "$worker" >/dev/null || true
    base_url="$(worker_base_url "${AVAILABLE_WORKER_ADDRESS:-$worker.local}")"
    if curl -fs --max-time 5 "$base_url/unit_api/system/utc_clock" >/dev/null; then
      ok "worker $worker API is available"
      return 0
    fi
    sleep 2
  done

  fail "worker $worker API did not become available after add-back"
  return 1
}

patch_unit_specific_config() {
  local worker="$1"
  local code_file="$2"
  local payload_file
  payload_file="$(mktemp)"

  if ! json_file_for_code_patch "$code_file" "$payload_file"; then
    rm -f "$payload_file"
    return 1
  fi

  curl -fsS \
    -X PATCH \
    -H "Content-Type: application/json" \
    -d "@$payload_file" \
    "http://localhost/api/config/units/$worker/specific" >/dev/null
  local status=$?
  rm -f "$payload_file"
  return "$status"
}

append_config_smoke_section() {
  # Usage: append_config_smoke_section INPUT_FILE OUTPUT_FILE SECTION_NAME WORKER_NAME
  local input_file="$1"
  local output_file="$2"
  local section_name="$3"
  local worker="$4"

  python3 - "$input_file" "$output_file" "$section_name" "$worker" <<'PY'
import pathlib
import sys

source = pathlib.Path(sys.argv[1])
target = pathlib.Path(sys.argv[2])
section_name = sys.argv[3]
worker = sys.argv[4]

text = source.read_text(encoding="utf-8")
if text and not text.endswith("\n"):
    text += "\n"
text += f"\n[{section_name}]\nworker_target={worker}\n"
target.write_text(text, encoding="utf-8")
PY
}

worker_specific_config_has_section() {
  local worker="$1"
  local section_name="$2"
  local config_json

  if ! config_json="$(curl -fsS "http://localhost/api/config/units/$worker")"; then
    return 1
  fi

  CONFIG_JSON="$config_json" python3 - "$worker" "$section_name" <<'PY'
import json
import os
import sys

worker = sys.argv[1]
section = sys.argv[2]
payload = json.loads(os.environ["CONFIG_JSON"])
config = payload.get("configs", {}).get(worker, {})
sys.exit(0 if section in config else 1)
PY
}

worker_plugin_list_contains() {
  local base_url="$1"
  local plugin_name="$2"
  local plugins_json

  if ! plugins_json="$(curl -fs "$base_url/unit_api/plugins/installed")"; then
    return 1
  fi

PLUGINS_JSON="$plugins_json" python3 - "$plugin_name" <<'PY'
import json
import os
import sys

plugin_name = sys.argv[1].replace("-", "_")
plugins = json.loads(os.environ["PLUGINS_JSON"])
sys.exit(0 if any(str(plugin.get("name") or "").replace("-", "_") == plugin_name for plugin in plugins) else 1)
PY
}

wait_for_worker_plugin() {
  local base_url="$1"
  local plugin_name="$2"

  for _ in {1..24}; do
    if worker_plugin_list_contains "$base_url" "$plugin_name"; then
      return 0
    fi
    sleep 2
  done

  return 1
}

wait_for_worker_plugin_absent() {
  local base_url="$1"
  local plugin_name="$2"

  for _ in {1..24}; do
    if worker_plugin_list_contains "$base_url" "$plugin_name"; then
      sleep 2
    else
      return 0
    fi
  done

  return 1
}

print_prefixed_file_excerpt() {
  local prefix="$1"
  local file="$2"
  local max_bytes="${3:-4000}"

  if [[ -s "$file" ]]; then
    head -c "$max_bytes" "$file" | while IFS= read -r line || [[ -n "$line" ]]; do
      warn "$prefix$line"
    done
  else
    warn "$prefix<empty>"
  fi
}

write_worker_plugin_install_diagnostics() {
  local worker="$1"
  local base_url="$2"
  local plugin_name="$3"
  local dispatch_response_file="$4"
  local plugins_file logs_file system_logs_file

  plugins_file="$(mktemp)"
  logs_file="$(mktemp)"
  system_logs_file="$(mktemp)"

  warn "Diagnostics for $plugin_name install on $worker"
  warn "Install dispatch response:"
  print_prefixed_file_excerpt "  " "$dispatch_response_file" 2000

  if curl -fsS "$base_url/unit_api/plugins/installed" > "$plugins_file"; then
    warn "Worker /unit_api/plugins/installed response:"
    print_prefixed_file_excerpt "  " "$plugins_file" 4000
  else
    warn "Unable to fetch worker /unit_api/plugins/installed"
  fi

  if curl -fsS "http://localhost/api/units/$worker/logs?min_level=DEBUG" > "$logs_file"; then
    warn "Recent leader-captured unit logs for $worker:"
    print_prefixed_file_excerpt "  " "$logs_file" 4000
  else
    warn "Unable to fetch /api/units/$worker/logs"
  fi

  if curl -fsS "http://localhost/api/units/$worker/system_logs?min_level=DEBUG" > "$system_logs_file"; then
    warn "Recent leader-captured system logs for $worker:"
    print_prefixed_file_excerpt "  " "$system_logs_file" 4000
  else
    warn "Unable to fetch /api/units/$worker/system_logs"
  fi

  rm -f "$plugins_file" "$logs_file" "$system_logs_file"
}

wait_for_worker_task_success() {
  local base_url="$1"
  local dispatch_response_file="$2"
  local result_file="$3"
  local description="$4"
  local max_attempts="${5:-90}"
  local sleep_seconds="${6:-2}"
  local progress_every_attempts="${7:-15}"
  local result_url_path task_state attempt elapsed_seconds

  if ! result_url_path="$(python3 - "$dispatch_response_file" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload.get("result_url_path") or "")
PY
)"; then
    fail "unable to parse $description task response"
    return 1
  fi

  if [[ -z "$result_url_path" ]]; then
    fail "$description task response missing result_url_path"
    return 1
  fi

  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if ! curl -fs "$base_url$result_url_path" > "$result_file"; then
      if (( attempt % progress_every_attempts == 0 )); then
        elapsed_seconds=$((attempt * sleep_seconds))
        warn "$description task result unavailable after ${elapsed_seconds}s"
      fi
      sleep "$sleep_seconds"
      continue
    fi

    task_state="$(TASK_JSON="$(cat "$result_file")" python3 <<'PY'
import json
import os

payload = json.loads(os.environ["TASK_JSON"])
status = payload.get("status")
if status in {"pending", "running"}:
    print(status)
elif status == "succeeded" and payload.get("result") is True:
    print("succeeded_true")
elif status == "succeeded" and payload.get("result") is not False:
    print("succeeded")
elif status == "succeeded":
    print("succeeded_false")
elif status == "failed":
    print("failed")
else:
    print(status or "unknown")
PY
)"

    case "$task_state" in
      succeeded|succeeded_true)
        ok "$description task succeeded"
        return 0
        ;;
      succeeded_false|failed)
        fail "$description task completed with status $task_state"
        return 1
        ;;
    esac

    if (( attempt % progress_every_attempts == 0 )); then
      elapsed_seconds=$((attempt * sleep_seconds))
      warn "$description task still $task_state after ${elapsed_seconds}s"
      print_prefixed_file_excerpt "  task result: " "$result_file" 1200
    fi

    sleep "$sleep_seconds"
  done

  fail "$description task did not complete"
  return 1
}

worker_running_jobs_contain() {
  local base_url="$1"
  local job_name="$2"
  local jobs_json

  if ! jobs_json="$(curl -fs "$base_url/unit_api/jobs/running")"; then
    return 1
  fi

  JOBS_JSON="$jobs_json" python3 - "$job_name" <<'PY'
import json
import os
import sys

job_name = sys.argv[1]
jobs = json.loads(os.environ["JOBS_JSON"])
sys.exit(0 if any(job.get("job_name") == job_name for job in jobs) else 1)
PY
}

get_worker_experiment_assignment() {
  local worker="$1"
  local response_file status
  response_file="$(mktemp)"

  status="$(curl -sS -o "$response_file" -w "%{http_code}" "http://localhost/api/workers/$worker/experiment")"
  case "$status" in
    200)
      python3 - "$response_file" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload.get("experiment") or "")
PY
      rm -f "$response_file"
      return 0
      ;;
    404)
      rm -f "$response_file"
      return 0
      ;;
    *)
      rm -f "$response_file"
      return 1
      ;;
  esac
}

get_worker_dot_pioreactor_root() {
  local base_url="$1"
  local path_json

  if ! path_json="$(curl -fsS "$base_url/unit_api/system/path/")"; then
    return 1
  fi

  PATH_JSON="$path_json" python3 <<'PY'
import json
import os

payload = json.loads(os.environ["PATH_JSON"])
print(payload["current"])
PY
}

restore_temporary_worker_experiment_assignment() {
  local worker="$1"
  local experiment="$2"

  if pio workers unassign "$worker" "$experiment" >/dev/null; then
    ok "unassigned $worker from temporary experiment $experiment"
  else
    fail "failed to unassign $worker from temporary experiment $experiment"
  fi

  if pio experiments delete "$experiment" --yes >/dev/null; then
    ok "deleted temporary experiment $experiment"
  else
    fail "failed to delete temporary experiment $experiment"
  fi
}

pause_for_job_sync() {
  sleep "$JOB_SYNC_DELAY"
}

cleanup() {
  if [[ "$VERIFIED_IDLE_BEFORE" == true ]]; then
    info "Ensuring all jobs are stopped"
    pio kill --all-jobs >/dev/null || true
  fi
}

trap cleanup EXIT

run_tests() {
  local tests_to_run=()

  if ((${#SELECTED_TESTS[@]} > 0)); then
    tests_to_run=("${SELECTED_TESTS[@]}")
  else
    tests_to_run=("${TEST_SEQUENCE[@]}")
  fi

  for test_func in "${tests_to_run[@]}"; do
    if ! declare -F "$test_func" >/dev/null; then
      fail "Unknown test: $test_func"
      continue
    fi

    "$test_func"
  done
}

check_versions() {
  run_step "Checking Pioreactor versions" pio version -v
}

check_configuration_files() {
  local config_dir="$HOME/.pioreactor"
  local hostname
  hostname="$(hostname)"
  local files=(
    "$config_dir/unit_config.ini"
    "$config_dir/config.ini"
  )

  info "Validating Pioreactor configuration files in $config_dir"

  for file in "${files[@]}"; do
    if [[ ! -f "$file" ]]; then
      fail "Missing configuration file: $file"
      continue
    fi

    if crudini --get "$file" >/dev/null 2>&1; then
      ok "$file present with valid syntax"
    else
      fail "Invalid INI syntax in $file"
    fi
  done
}

check_config_api_endpoints() {
  local hostname
  hostname="$(hostname)"

  run_step \
    "Checking /unit_api/config/merged" \
    curl_check \
    http://localhost/unit_api/config/merged \
    'type=="object" and has("cluster.topology") and has("mqtt")'
  run_step "Checking /unit_api/config/specific" curl_ok http://localhost/unit_api/config/specific
  run_step \
    "Checking /api/config/units/$hostname" \
    curl_check \
    "http://localhost/api/config/units/$hostname" \
    "type==\"object\" and (.configs | type==\"object\" and has(\"$hostname\") and (.[\"$hostname\"] | type==\"object\" and has(\"cluster.topology\"))) and (.errors | type==\"object\" and length==0)"
  run_step \
    "Checking /api/config/units/\$broadcast" \
    curl_check \
    http://localhost/api/config/units/\$broadcast \
    'type=="object" and (.configs | type=="object" and has("'"$hostname"'")) and (.errors | type=="object")'
  run_step \
    "Checking /api/config/units/$hostname/specific" \
    curl_ok \
    "http://localhost/api/config/units/$hostname/specific"
}

check_services() {
  local services=(mosquitto lighttpd huey)

  if [[ "$HAS_SYSTEMCTL" != true ]]; then
    warn "systemctl not available; skipping service checks"
    return
  fi

  for service in "${services[@]}"; do
    info "Checking service: $service"
    if systemctl is-active --quiet "$service"; then
      ok "$service active"
    else
      fail "$service not active"
    fi
  done
}

check_runtime_packaging() {
  info "Checking runtime packaging (mosquitto clients, Huey workers, boot partition imports)"

  if command -v mosquitto_sub >/dev/null 2>&1 && command -v mosquitto_pub >/dev/null 2>&1; then
    ok "mosquitto clients installed"
  else
    fail "mosquitto clients missing; they are installed on every unit"
  fi

  # Calibration steps run as a Huey task that waits on other Huey tasks, so one worker deadlocks.
  local huey_launcher="/usr/local/bin/start_pioreactor_huey.sh"
  if [[ ! -f "$huey_launcher" ]]; then
    warn "$huey_launcher not found; skipping Huey worker count check"
  elif grep -Eq 'huey_consumer.*[[:space:]]-w[[:space:]]+1([[:space:]]|$)' "$huey_launcher"; then
    fail "$huey_launcher starts a single Huey worker; calibration session steps need at least two"
  else
    ok "Huey launcher starts at least two workers for every image profile"
  fi

  if ! grep -qs 'Raspberry Pi' /proc/device-tree/model; then
    warn "Not a Raspberry Pi image; skipping boot partition import checks"
    return
  fi

  if [[ "$HAS_SYSTEMCTL" != true ]]; then
    warn "systemctl not available; skipping boot partition import checks"
    return
  fi

  local target_wants service
  target_wants="$(systemctl show -p Wants --value pioreactor.target 2>/dev/null)"
  for service in bootfs_plugins bootfs_files; do
    if ! systemctl cat "$service.service" >/dev/null 2>&1; then
      fail "$service.service is not installed"
      continue
    fi

    if [[ -x "/usr/local/bin/$service.sh" ]]; then
      ok "/usr/local/bin/$service.sh installed"
    else
      fail "/usr/local/bin/$service.sh missing or not executable"
    fi

    if grep -qw "$service.service" <<< "$target_wants"; then
      ok "pioreactor.target pulls in $service.service"
    else
      fail "pioreactor.target does not pull in $service.service"
    fi

    if systemctl is-failed --quiet "$service.service"; then
      fail "$service.service failed this boot; see: journalctl -u $service.service"
    else
      ok "$service.service did not fail this boot"
    fi
  done

  if systemctl cat bootfs_plugins.path >/dev/null 2>&1; then
    fail "retired bootfs_plugins.path is still installed"
  fi

  local boot_dir="/boot/firmware/pioreactor" leftovers
  if [[ -d "$boot_dir" ]]; then
    leftovers="$(find "$boot_dir" -type f \( -name '*.log' -o -path '*/failed/*' \) 2>/dev/null | head -n 5)"
    if [[ -n "$leftovers" ]]; then
      warn "Boot partition has failed imports awaiting correction:"
      while IFS= read -r line; do
        warn "  $line"
      done <<< "$leftovers"
    fi
  fi
}

check_ui_static_assets() {
  info "Checking UI entrypoint and built assets"

  local html javascript_path stylesheet_path
  if ! html="$(curl -fsS http://localhost/)"; then
    fail "UI entrypoint request failed"
    return
  fi

  javascript_path="$(grep -Eo '/static/static/[^"]+\.js' <<< "$html" | head -n 1)"
  stylesheet_path="$(grep -Eo '/static/static/[^"]+\.css' <<< "$html" | head -n 1)"
  if [[ -z "$javascript_path" || -z "$stylesheet_path" ]]; then
    fail "UI entrypoint did not reference built JavaScript and CSS assets"
    return
  fi

  if curl -fsS "http://localhost${javascript_path}" >/dev/null && \
     curl -fsS "http://localhost${stylesheet_path}" >/dev/null; then
    ok "UI entrypoint references loadable JavaScript and CSS assets"
  else
    fail "UI JavaScript or CSS asset failed to load"
  fi
}

check_kiosk_route() {
  info "Checking the touchscreen UI served under /k/"

  local kiosk_html path cache_control javascript_path
  if http_status_is 404 http://localhost/static/kiosk.html; then
    warn "kiosk.html is not part of the installed UI build; skipping /k/ checks"
    return
  fi

  if ! kiosk_html="$(curl -fsS http://localhost/static/kiosk.html)"; then
    fail "/static/kiosk.html request failed"
    return
  fi

  for path in /k /k/ /k/agent/smoke "/k?agent=smoke"; do
    if [[ "$(curl -fsS "http://localhost$path")" == "$kiosk_html" ]]; then
      ok "$path serves kiosk.html"
    else
      fail "$path does not serve kiosk.html"
    fi
  done

  # A cached shell would keep pointing at hashed assets that an update removed.
  for path in /k/ /static/kiosk.html; do
    cache_control="$(http_header_value Cache-Control "http://localhost$path")"
    if [[ "$cache_control" == *no-store* ]]; then
      ok "$path is served with Cache-Control: no-store"
    else
      fail "$path Cache-Control is '${cache_control:-<missing>}', expected no-store"
    fi
  done

  javascript_path="$(grep -Eo '/static/static/[^"]+\.js' <<< "$kiosk_html" | head -n 1)"
  if [[ -n "$javascript_path" ]] && curl -fsS "http://localhost${javascript_path}" >/dev/null; then
    ok "kiosk.html references a loadable JavaScript bundle"
  else
    fail "kiosk.html does not reference a loadable JavaScript bundle"
  fi
}

check_mqtt_logging() {
  run_step "Logging a test message to MQTT" pio log -m "agent_smoke: hello from $(hostname)"
}

check_monitor_job() {
  info "Verifying monitor job is running"
  local jobs_json
  if ! jobs_json="$(fetch_running_jobs)"; then
    fail "Unable to fetch running jobs"
    return
  fi

  if jobs_contain "$jobs_json" 'any(.job_name=="monitor")'; then
    ok "monitor job is running"
  else
    fail "monitor job is not running"
  fi

  VERIFIED_IDLE_BEFORE=true
}

check_database_access() {
  info "Checking database accessibility (leader only)"
  if pio db <<< '.tables' | grep -qi workers; then
    ok "database reachable and has workers table"
  else
    warn "database CLI not available or table not found"
  fi
}

check_worker_model_metadata() {
  local hostname query result model_name model_version fix_command

  hostname="$(hostname)"
  info "Inspecting worker model metadata for ${hostname}"

  read -r -d '' query <<SQL || true
.headers off
.mode list
SELECT COALESCE(model_name, ''), COALESCE(model_version, '')
FROM workers
WHERE pioreactor_unit = '${hostname}'
LIMIT 1;
SQL

  if ! result="$(pio db <<< "$query" 2>/dev/null | head -n 1)"; then
    fail "Unable to query worker model metadata via 'pio db'"
    return
  fi

  if [[ -z "$result" ]]; then
    fail "No workers entry found for ${hostname} in database"
    return
  fi

  IFS='|' read -r model_name model_version <<< "$result"

  if [[ -z "${model_name// }" || -z "${model_version// }" ]]; then
    fix_command="pio workers model set ${hostname} pioreactor_40ml 1.5"
    fail "Worker model metadata missing for ${hostname}. Populate it with: ${fix_command}"
    return
  fi

  ok "Worker ${hostname} registered as ${model_name} v${model_version}"
}

check_unit_model_contract() {
  local hostname local_model model_name model_version model_filter payload
  hostname="$(hostname)"

  info "Checking the unit-owned model assignment"
  if [[ "$HAS_JQ" != true ]]; then
    warn "jq not installed; skipping unit model checks"
    return
  fi

  if ! local_model="$(pio model get)"; then
    fail "pio model get failed"
    return
  fi

  model_name="$(jq -r '.model_name // empty' <<< "$local_model")"
  model_version="$(jq -r '.model_version // empty' <<< "$local_model")"
  if [[ -z "$model_name" || -z "$model_version" ]]; then
    fail "No model saved on ${hostname}. Set it with: pio model set <model_name> <model_version>"
    return
  fi
  ok "pio model get reports ${model_name} v${model_version}"

  model_filter=".model_name==\"$model_name\" and .model_version==\"$model_version\" and (.display_name | type==\"string\") and (.reactor_capacity_ml | type==\"number\") and (.reactor_max_fill_volume_ml | type==\"number\")"
  run_step \
    "Checking /unit_api/model returns the local model definition" \
    curl_check \
    http://localhost/unit_api/model \
    "$model_filter"
  run_step \
    "Checking /api/workers/$hostname/model matches the unit's model" \
    curl_check \
    "http://localhost/api/workers/$hostname/model" \
    "$model_filter and .pioreactor_unit==\"$hostname\""
  run_step \
    "Checking leader inventory mirrors the unit's model" \
    curl_check \
    http://localhost/api/workers \
    "any(.[]; .pioreactor_unit==\"$hostname\" and .model_name==\"$model_name\" and .model_version==\"$model_version\")"

  payload="{\"model_name\":\"$model_name\",\"model_version\":\"$model_version\"}"
  run_step \
    "Checking PUT /api/workers/$hostname/reported_model accepts the current model" \
    http_status_is \
    200 \
    "http://localhost/api/workers/$hostname/reported_model" \
    -X PUT \
    -H "Content-Type: application/json" \
    -d "$payload"
  run_step \
    "Checking PUT /unit_api/model rejects an unknown model" \
    http_status_is \
    400 \
    http://localhost/unit_api/model \
    -X PUT \
    -H "Content-Type: application/json" \
    -d '{"model_name":"agent_smoke_unknown_model","model_version":"0.0"}'
  run_step \
    "Checking /unit_api/model is unchanged after the rejected update" \
    curl_check \
    http://localhost/unit_api/model \
    "$model_filter"

  if pio cache list | grep -qx pioreactor_model; then
    ok "pio cache list includes pioreactor_model"
  else
    fail "pio cache list does not include pioreactor_model"
  fi

  if ! no_short_lived_jobs_running; then
    warn "Activities are running; skipping idempotent pio model set"
    return
  fi

  local set_output
  if set_output="$(pio model set "$model_name" "$model_version")" && \
     jq -e ".model_name==\"$model_name\" and .model_version==\"$model_version\"" <<< "$set_output" >/dev/null; then
    ok "pio model set re-saved ${model_name} v${model_version}"
  else
    fail "pio model set ${model_name} ${model_version} failed"
  fi
}

check_unit_api_core() {
  run_step "Checking /unit_api/versions/app" curl_check http://localhost/unit_api/versions/app
  run_step "Checking /unit_api/jobs/running" curl_check http://localhost/unit_api/jobs/running 'type=="array"'
  run_step "Checking /unit_api/capabilities" curl_check http://localhost/unit_api/capabilities
  run_step \
    "Checking /unit_api/system/utc_clock" \
    curl_check \
    http://localhost/unit_api/system/utc_clock \
    '(.clock_time | type=="string") and has("synchronized") and (.synchronized | type=="boolean" or type=="null")'
  run_step \
    "Checking /unit_api/system/ipv4" \
    curl_check \
    http://localhost/unit_api/system/ipv4 \
    '.ipv4_address | type=="string" and length>0 and (split(",") | all(test("^[0-9]{1,3}(\\.[0-9]{1,3}){3}$")))'
  run_step \
    "Checking camera manual-focus protocol registration" \
    curl_check \
    http://localhost/unit_api/calibration_protocols \
    'type=="array" and any(.target_device=="camera" and .protocol_name=="manual_focus")'
  run_step "Checking /unit_api/calibrations" curl_check http://localhost/unit_api/calibrations
  run_step "Checking /unit_api/active_calibrations" curl_check http://localhost/unit_api/active_calibrations
}

check_registered_target_validation() {
  run_step \
    "Checking config proxy rejects address target" \
    http_status_is \
    400 \
    http://localhost/api/config/units/203.0.113.10/specific
  run_step \
    "Checking system fanout rejects address target" \
    http_status_is \
    400 \
    http://localhost/api/units/203.0.113.10/system/reboot \
    -H "Content-Length: 0" \
    -X POST
}

# A stop request that matches no jobs: harmless if a guard under test fails open.
NOOP_STOP_PAYLOAD='{"experiment":"agent-smoke-no-such-experiment"}'

check_mutation_target_guard() {
  local hostname
  hostname="$(hostname)"

  run_step \
    "Checking /unit_api rejects writes addressed to another unit" \
    http_status_is \
    409 \
    http://localhost/unit_api/jobs/stop \
    -X PATCH \
    -H "Content-Type: application/json" \
    -H "X-Pioreactor-Target: agent-smoke-not-$hostname" \
    -d "$NOOP_STOP_PAYLOAD"
  run_step \
    "Checking /unit_api accepts writes addressed to $hostname" \
    http_status_is \
    202 \
    http://localhost/unit_api/jobs/stop \
    -X PATCH \
    -H "Content-Type: application/json" \
    -H "X-Pioreactor-Target: $hostname" \
    -d "$NOOP_STOP_PAYLOAD"
  run_step \
    "Checking /unit_api accepts writes without a target header" \
    http_status_is \
    202 \
    http://localhost/unit_api/jobs/stop \
    -X PATCH \
    -H "Content-Type: application/json" \
    -d "$NOOP_STOP_PAYLOAD"
  run_step \
    "Checking /unit_api reads ignore a mismatched target" \
    http_status_is \
    200 \
    http://localhost/unit_api/jobs/running \
    -H "X-Pioreactor-Target: agent-smoke-not-$hostname"
  run_step \
    "Checking renamed remove_from_inventory route is gone" \
    http_status_is \
    404 \
    "http://localhost/unit_api/system/remove_from_inventory/agent-smoke-not-$hostname" \
    -X POST \
    -H "Content-Length: 0"
}

check_cross_site_write_protection() {
  local hostname foreign_origin cluster_origin allow_origin allow_headers vary
  hostname="$(hostname)"
  foreign_origin="https://agent-smoke.invalid"
  cluster_origin="http://$hostname.local"

  info "Testing CORS and cross-site write protection"

  allow_origin="$(http_header_value Access-Control-Allow-Origin http://localhost/api/workers -H "Origin: $cluster_origin")"
  if [[ "$allow_origin" == "$cluster_origin" ]]; then
    ok "/api allows reads from cluster origin $cluster_origin"
  else
    fail "/api Access-Control-Allow-Origin for $cluster_origin was '${allow_origin:-<missing>}'"
  fi

  allow_origin="$(http_header_value Access-Control-Allow-Origin http://localhost/api/workers -H "Origin: http://localhost:5173")"
  if [[ "$allow_origin" == "http://localhost:5173" ]]; then
    ok "/api allows reads from localhost on any port"
  else
    fail "/api Access-Control-Allow-Origin for http://localhost:5173 was '${allow_origin:-<missing>}'"
  fi

  allow_origin="$(http_header_value Access-Control-Allow-Origin http://localhost/api/workers -H "Origin: $foreign_origin")"
  if [[ -z "$allow_origin" ]]; then
    ok "/api sends no CORS headers to foreign origins"
  else
    fail "/api allowed foreign origin $foreign_origin ($allow_origin)"
  fi

  allow_origin="$(http_header_value Access-Control-Allow-Origin http://localhost/api/workers -H "Origin: $cluster_origin:8080")"
  if [[ -z "$allow_origin" ]]; then
    ok "/api rejects cluster origins on non-default ports"
  else
    fail "/api allowed $cluster_origin:8080 ($allow_origin)"
  fi

  vary="$(http_header_value Vary http://localhost/api/workers -H "Origin: $foreign_origin")"
  if [[ "${vary,,}" == *origin* ]]; then
    ok "/api responses vary on Origin"
  else
    fail "/api Vary header was '${vary:-<missing>}', expected Origin"
  fi

  allow_headers="$(http_header_value Access-Control-Allow-Headers http://localhost/api/workers \
    -X OPTIONS \
    -H "Origin: $cluster_origin" \
    -H "Access-Control-Request-Method: PUT" \
    -H "Access-Control-Request-Headers: content-type, x-pioreactor-target")"
  if [[ "$allow_headers" == *X-Pioreactor-Target* ]]; then
    ok "/api preflight allows the X-Pioreactor-Target header"
  else
    fail "/api preflight Access-Control-Allow-Headers was '${allow_headers:-<missing>}'"
  fi

  run_step \
    "Checking /unit_api rejects browser writes from foreign origins" \
    http_status_is \
    403 \
    http://localhost/unit_api/jobs/stop \
    -X PATCH \
    -H "Content-Type: application/json" \
    -H "Origin: $foreign_origin" \
    -d "$NOOP_STOP_PAYLOAD"
  run_step \
    "Checking /unit_api rejects simple form posts from foreign origins" \
    http_status_is \
    403 \
    http://localhost/unit_api/jobs/stop \
    -X POST \
    -H "Origin: $foreign_origin" \
    --data-urlencode "experiment=agent-smoke-no-such-experiment"
  run_step \
    "Checking /unit_api accepts browser writes from localhost" \
    http_status_is \
    202 \
    http://localhost/unit_api/jobs/stop \
    -X PATCH \
    -H "Content-Type: application/json" \
    -H "Origin: http://localhost" \
    -d "$NOOP_STOP_PAYLOAD"

  if [[ "$HAS_JQ" != true ]]; then
    warn "jq not installed; skipping /api cross-site write checks"
    return
  fi

  local local_model model_payload
  if ! local_model="$(pio model get)" || \
     ! jq -e '.model_name and .model_version' <<< "$local_model" >/dev/null; then
    warn "No local model saved; skipping /api cross-site write checks"
    return
  fi
  model_payload="$(jq -c '{model_name, model_version}' <<< "$local_model")"

  run_step \
    "Checking /api rejects browser writes from foreign origins" \
    http_status_is \
    403 \
    "http://localhost/api/workers/$hostname/reported_model" \
    -X PUT \
    -H "Content-Type: application/json" \
    -H "Origin: $foreign_origin" \
    -d "$model_payload"
  run_step \
    "Checking /api accepts browser writes from cluster origin $cluster_origin" \
    http_status_is \
    200 \
    "http://localhost/api/workers/$hostname/reported_model" \
    -X PUT \
    -H "Content-Type: application/json" \
    -H "Origin: $cluster_origin" \
    -d "$model_payload"
  run_step \
    "Checking /api accepts writes without an Origin" \
    http_status_is \
    200 \
    "http://localhost/api/workers/$hostname/reported_model" \
    -X PUT \
    -H "Content-Type: application/json" \
    -d "$model_payload"
}

check_usb_status_surface() {
  local hostname
  hostname="$(hostname)"

  run_step \
    "Checking /unit_api/usb status shape" \
    curl_check \
    http://localhost/unit_api/usb \
    '. as $p | type=="object" and (["absent","present_unmounted","mounted","mounted_readonly","multiple_present","unsupported","error"] | index($p.status) != null) and ($p.partitions | type=="array") and ($p | has("active_mount"))'

  run_step \
    "Checking /unit_api/usb/artifacts handles current USB state" \
    usb_artifacts_endpoint_ok

  run_step \
    "Checking /api/units/$hostname/usb target route" \
    curl_check \
    "http://localhost/api/units/$hostname/usb"

}

usb_artifacts_endpoint_ok() {
  local response_file status
  response_file="$(mktemp)"
  status="$(curl -sS -o "$response_file" -w "%{http_code}" http://localhost/unit_api/usb/artifacts)"

  case "$status" in
    200)
      if [[ "$HAS_JQ" == true ]]; then
        jq -e 'type=="object" and (.mountpoint | type=="string") and (.updates | type=="array") and (.plugins | type=="array")' "$response_file" >/dev/null
      else
        [[ -s "$response_file" ]]
      fi
      ;;
    400)
      [[ -s "$response_file" ]]
      ;;
    *)
      rm -f "$response_file"
      return 1
      ;;
  esac

  local result=$?
  rm -f "$response_file"
  return "$result"
}

check_descriptor_endpoints() {
  run_step \
    "Checking /unit_api/jobs/descriptors" \
    curl_check \
    http://localhost/unit_api/jobs/descriptors \
    'type=="array" and any(.job_name=="stirring") and any(.job_name=="self_test" and any(.published_settings[]; .key=="test_dark_offset_correction_is_effective"))'
  run_step \
    "Checking /unit_api/automations/descriptors/dosing" \
    curl_check \
    http://localhost/unit_api/automations/descriptors/dosing \
    'type=="array" and any(.automation_name=="chemostat") and any(.automation_name=="turbidostat")'
  run_step \
    "Checking /api/jobs/descriptors" \
    curl_check \
    http://localhost/api/jobs/descriptors \
    'type=="array" and any(.job_name=="stirring")'
  run_step \
    "Checking /api/automations/descriptors/dosing" \
    curl_check \
    http://localhost/api/automations/descriptors/dosing \
    'type=="array" and any(.automation_name=="chemostat")'
}

check_calibration_session_tasks() {
  # The stirring DC-based intro step advances without hardware; the session is aborted
  # before its "Run calibration" step.
  local hostname sessions_url response_file status session_id task_id task_status
  hostname="$(hostname)"
  sessions_url="http://localhost/api/workers/$hostname/calibrations/sessions"

  info "Testing calibration session steps run as Huey tasks"
  if [[ "$HAS_JQ" != true ]]; then
    warn "jq not installed; skipping calibration session checks"
    return
  fi

  local jobs_json
  if ! jobs_json="$(fetch_running_jobs)"; then
    fail "Unable to fetch running jobs"
    return
  fi
  if jobs_contain "$jobs_json" 'any(.[]; .job_name=="stirring")'; then
    warn "stirring is running; skipping calibration session checks"
    return
  fi

  response_file="$(mktemp)"
  status="$(curl -sS -o "$response_file" -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{"target_device":"stirring","protocol_name":"dc_based"}' \
    "$sessions_url")"
  session_id="$(jq -r '.session.session_id // empty' "$response_file" 2>/dev/null)"
  if [[ "$status" == "201" && -n "$session_id" ]] && \
     jq -e '.step.step_id=="intro"' "$response_file" >/dev/null; then
    ok "started stirring calibration session $session_id"
  else
    fail "starting a stirring calibration session returned HTTP $status"
    print_prefixed_file_excerpt "session start response: " "$response_file" 2000
    rm -f "$response_file"
    return
  fi

  status="$(curl -sS -o "$response_file" -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{"inputs":{}}' \
    "$sessions_url/$session_id/inputs")"
  task_id="$(jq -r '.task_id // empty' "$response_file" 2>/dev/null)"
  if [[ "$status" == "202" && -n "$task_id" ]] && \
     jq -e '.status=="accepted" and (.result_url_path | type=="string")' "$response_file" >/dev/null; then
    ok "advancing the session answered 202 with task $task_id"
  else
    fail "advancing the session returned HTTP $status, expected 202 with a task"
    print_prefixed_file_excerpt "session inputs response: " "$response_file" 2000
    task_id=""
  fi

  if [[ -n "$task_id" ]]; then
    for _ in {1..60}; do
      if curl -fsS "http://localhost/api/workers/$hostname/task_results/$task_id" > "$response_file"; then
        task_status="$(jq -r '.status // empty' "$response_file")"
        [[ "$task_status" == "succeeded" || "$task_status" == "failed" ]] && break
      fi
      sleep 0.5
    done

    if jq -e '.status=="succeeded" and .result.session.step_id=="run_calibration" and .result.step.step_id=="run_calibration"' \
      "$response_file" >/dev/null; then
      ok "session step task succeeded with {session, step} result"
    else
      fail "session step task did not succeed with the next step (last status: ${task_status:-unknown})"
      print_prefixed_file_excerpt "task result: " "$response_file" 2000
    fi

    run_step \
      "Checking the stored session advanced" \
      curl_check \
      "$sessions_url/$session_id" \
      '.step.step_id=="run_calibration"'
  fi

  if curl -fsS -X POST -H "Content-Length: 0" "$sessions_url/$session_id/abort" > "$response_file" && \
     jq -e '.session.status=="aborted"' "$response_file" >/dev/null; then
    ok "aborted calibration session $session_id"
  else
    fail "unable to abort calibration session $session_id"
    print_prefixed_file_excerpt "session abort response: " "$response_file" 2000
  fi

  rm -f "$response_file"
}

check_camera_contract() {
  local hostname camera_enabled snapshot_interval probe_experiment
  local status_file listing_file archive_file dispatch_file task_result_file
  local initial_auto_capture_enabled auto_capture_setting_was_persisted=false target
  local -a auto_capture_targets
  hostname="$(hostname)"
  probe_experiment="agent-smoke-camera-${hostname}-$(date +%s)-$$"
  status_file="$(mktemp)"
  listing_file="$(mktemp)"
  archive_file="$(mktemp)"
  dispatch_file="$(mktemp)"
  task_result_file="$(mktemp)"

  info "Testing camera configuration and API contract"
  if ! camera_enabled="$(pio config get camera enabled 2>/dev/null)" || \
     ! snapshot_interval="$(pio config get camera snapshot_interval_minutes 2>/dev/null)"; then
    fail "camera config was not installed into the merged configuration"
    rm -f "$status_file" "$listing_file" "$archive_file" "$dispatch_file" "$task_result_file"
    return
  fi
  camera_enabled="${camera_enabled//[[:space:]]/}"
  snapshot_interval="${snapshot_interval//[[:space:]]/}"
  if [[ "$camera_enabled" =~ ^[01]$ && "$snapshot_interval" =~ ^[0-9]+$ ]]; then
    ok "camera config is installed (enabled=$camera_enabled, interval=$snapshot_interval)"
  else
    fail "camera config contains invalid enabled or snapshot interval values"
  fi

  if ! python3_available; then
    warn "python3 not available; skipping structured camera contract checks"
    rm -f "$status_file" "$listing_file" "$archive_file" "$dispatch_file" "$task_result_file"
    return
  fi

  if curl -fsS \
    "http://localhost/api/workers/$hostname/camera/experiments/$probe_experiment/status" \
    > "$status_file" && \
    curl -fsS \
    "http://localhost/api/workers/$hostname/camera/experiments/$probe_experiment/stills" \
    > "$listing_file" && \
    curl -fsS \
    "http://localhost/api/workers/$hostname/camera/experiments/$probe_experiment/stills.zip" \
    > "$archive_file" && \
    python3 - "$status_file" "$listing_file" "$archive_file" "$hostname" "$probe_experiment" <<'PY'
import json
import pathlib
import sys
import zipfile

status_path, listing_path, archive_path, unit, experiment = sys.argv[1:]
status = json.loads(pathlib.Path(status_path).read_text(encoding="utf-8"))
assert status["unit"] == unit
assert status["detection_status"] in {"detected", "configured_camera_not_detected", "unknown"}
assert isinstance(status["runtime_available"], bool)
assert isinstance(status["auto_capture_enabled"], bool)
assert isinstance(status["snapshot_interval_minutes"], int)
assert status["snapshot_interval_minutes"] >= 0

expected_listing = {"unit": unit, "experiment": experiment, "stills": []}
assert json.loads(pathlib.Path(listing_path).read_text(encoding="utf-8")) == expected_listing
with zipfile.ZipFile(archive_path) as archive:
    assert archive.namelist() == ["camera_stills_manifest.json"]
    assert json.loads(archive.read("camera_stills_manifest.json")) == expected_listing
PY
  then
    ok "camera status, listing, and ZIP proxy contracts are valid"
  else
    fail "camera status, listing, or ZIP proxy contract is invalid"
    print_prefixed_file_excerpt "camera status response: " "$status_file" 2000
    rm -f "$status_file" "$listing_file" "$archive_file" "$dispatch_file" "$task_result_file"
    return
  fi

  initial_auto_capture_enabled="$(python3 - "$status_file" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if payload["auto_capture_enabled"] else "false")
PY
)"
  if pio cache view camera_settings auto_capture_enabled 2>/dev/null | \
    grep -q 'auto_capture_enabled'; then
    auto_capture_setting_was_persisted=true
  fi
  if [[ "$initial_auto_capture_enabled" == "true" ]]; then
    auto_capture_targets=(false true)
  else
    # Don't briefly enable scheduled captures when an operator has disabled them.
    auto_capture_targets=(false)
  fi

  for target in "${auto_capture_targets[@]}"; do
    if curl -fsS \
      -X PATCH \
      -H "Content-Type: application/json" \
      -d "{\"auto_capture_enabled\":$target}" \
      "http://localhost/api/workers/$hostname/camera/settings" \
      > "$dispatch_file" && \
      wait_for_worker_task_success \
        http://localhost "$dispatch_file" "$task_result_file" "camera auto-capture=$target" 30 1 10 && \
      curl -fsS \
        "http://localhost/api/workers/$hostname/camera/experiments/$probe_experiment/status" \
        > "$status_file" && \
      python3 - "$status_file" "$target" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["auto_capture_enabled"] is (sys.argv[2] == "true")
PY
    then
      ok "camera auto-capture setting round-tripped as $target"
    else
      fail "camera auto-capture setting did not round-trip as $target"
    fi
  done

  if ! curl -fsS \
    "http://localhost/api/workers/$hostname/camera/experiments/$probe_experiment/status" \
    > "$status_file" || \
    ! python3 - "$status_file" "$initial_auto_capture_enabled" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["auto_capture_enabled"] is (sys.argv[2] == "true")
PY
  then
    warn "camera setting was not restored through the leader; attempting local cleanup"
    curl -fsS \
      -X PATCH \
      -H "Content-Type: application/json" \
      -d "{\"auto_capture_enabled\":$initial_auto_capture_enabled}" \
      http://localhost/unit_api/camera/settings \
      >/dev/null || fail "unable to restore the original camera auto-capture setting"
  fi
  if [[ "$auto_capture_setting_was_persisted" == false ]]; then
    pio cache purge camera_settings auto_capture_enabled >/dev/null || \
      fail "unable to restore the camera setting's original default-backed state"
  fi

  if [[ "$camera_enabled" == "1" ]]; then
    local camera_experiment camera_experiment_path before_capture_file after_capture_file
    local capture_output captured_image_id image_file
    if ! python3 - "$status_file" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["runtime_available"] is True
assert payload["detection_status"] == "detected"
PY
    then
      fail "camera is enabled but its configured hardware is not detected"
    elif ! camera_experiment="$(get_worker_experiment_assignment "$hostname")"; then
      fail "unable to determine the current experiment assignment for camera capture"
    elif [[ -z "$camera_experiment" ]]; then
      warn "camera is available but no experiment is assigned; skipping physical capture"
    else
      camera_experiment_path="$(python3 - "$camera_experiment" <<'PY'
import sys
from urllib.parse import quote

print(quote(sys.argv[1], safe=""))
PY
)"
      before_capture_file="$(mktemp)"
      after_capture_file="$(mktemp)"
      image_file="$(mktemp)"
      if ! curl -fsS \
        "http://localhost/api/workers/$hostname/camera/experiments/$camera_experiment_path/stills" \
        > "$before_capture_file"; then
        fail "unable to list camera stills before capture"
      elif capture_output="$(pio run camera_snapshot 2>/dev/null)"; then
        captured_image_id="$(sed -n 's/^Captured camera snapshot \([^.]\{1,\}\)\.$/\1/p' <<< "$capture_output" | tail -n 1)"
        curl -fsS \
          "http://localhost/api/workers/$hostname/camera/experiments/$camera_experiment_path/stills" \
          > "$after_capture_file"
        if [[ -z "$captured_image_id" ]]; then
          captured_image_id="$(python3 - "$before_capture_file" "$after_capture_file" <<'PY'
import json
import pathlib
import sys

before = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
after = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
before_ids = {still["image_id"] for still in before["stills"]}
new_ids = [still["image_id"] for still in after["stills"] if still["image_id"] not in before_ids]
if len(new_ids) == 1:
    print(new_ids[0])
PY
)"
        fi

        if [[ -n "$captured_image_id" ]] && \
          curl -fsS \
            "http://localhost/api/workers/$hostname/camera/experiments/$camera_experiment_path/stills/$captured_image_id.jpg" \
            > "$image_file" && \
          python3 - "$after_capture_file" "$image_file" "$captured_image_id" <<'PY'
import json
import pathlib
import sys

listing = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert any(still["image_id"] == sys.argv[3] for still in listing["stills"])
image = pathlib.Path(sys.argv[2]).read_bytes()
assert len(image) > 100 and image.startswith(b"\xff\xd8")
PY
        then
          ok "camera_snapshot produced a listed JPEG through the leader proxy"
        else
          fail "camera_snapshot did not produce a retrievable experiment still"
        fi
      else
        fail "pio run camera_snapshot failed"
      fi

      if [[ -n "${captured_image_id:-}" ]]; then
        curl -fsS \
          -X DELETE \
          -H "Content-Length: 0" \
          "http://localhost/api/workers/$hostname/camera/experiments/$camera_experiment_path/stills/$captured_image_id.jpg" \
          >/dev/null || {
            fail "unable to delete camera smoke-test still through the leader proxy"
            curl -fsS \
              -X DELETE \
              -H "Content-Length: 0" \
              "http://localhost/unit_api/camera/experiments/$camera_experiment_path/stills/$captured_image_id.jpg" \
              >/dev/null || fail "unable to clean up camera smoke-test still $captured_image_id"
          }
      fi
      rm -f "$before_capture_file" "$after_capture_file" "$image_file"
    fi
  else
    warn "camera feature is disabled; skipping physical capture"
  fi

  rm -f "$status_file" "$listing_file" "$archive_file" "$dispatch_file" "$task_result_file"
}

check_unit_api_job_history() {
  run_step "Checking /unit_api/jobs" curl_check http://localhost/unit_api/jobs 'type=="array"'
}

check_blink() {
  run_step "Blinking device LED" pio blink
}

check_pio_run_latency() {
  info "Measuring pio run CLI startup time"

  local python_cmd
  if command -v python3 >/dev/null 2>&1; then
    python_cmd=python3
  else
    warn "python3 not available; skipping pio run latency check"
    return
  fi

  local measurement_raw
  measurement_raw="$("$python_cmd" <<'PY'
import subprocess
import sys
import time

start = time.perf_counter()
proc = subprocess.run(["pio", "run", "--help"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
elapsed = time.perf_counter() - start
print(f"{elapsed:.3f}")
sys.exit(proc.returncode)
PY
)"
  local status=$?

  if (( status != 0 )); then
    fail "pio run --help failed"
    return
  fi

  local measurement
  measurement="${measurement_raw//$'\n'/}"

  if [[ -z "$measurement" ]]; then
    fail "Unable to determine pio run latency"
    return
  fi

  if awk -v t="$measurement" 'BEGIN {exit (t < 1.5 ? 0 : 1)}'; then
    ok "pio run --help completed in ${measurement}s (<1.5s)"
  else
    fail "pio run --help took ${measurement}s (>=1.5s)"
  fi
}

check_pio_logs_cli() {
  info "Checking pio logs CLI"
  if pio logs -n 10 >/dev/null; then
    ok "pio logs CLI"
  else
    fail "pio logs CLI failed"
  fi
}

check_pio_usb_cli() {
  info "Checking pio usb CLI"

  if pio usb --help | grep -q "list"; then
    ok "pio usb exposes list subcommand"
  else
    fail "pio usb list subcommand missing"
  fi

  local usb_list
  if usb_list="$(pio usb list --json)"; then
    if [[ "$HAS_JQ" == true ]]; then
      if echo "$usb_list" | jq -e 'type=="array"' >/dev/null; then
        ok "pio usb list --json returns an array"
      else
        fail "pio usb list --json did not return an array"
      fi
    else
      ok "pio usb list --json responded"
    fi
  else
    fail "pio usb list --json failed"
  fi
}

check_update_cli_contract() {
  info "Checking CLI command shape"

  if pio jobs set --help >/dev/null; then
    ok "pio jobs set command available"
  else
    fail "pio jobs set command missing"
  fi

  if pios jobs set --help >/dev/null; then
    ok "pios jobs set command available"
  else
    fail "pios jobs set command missing"
  fi

  if pio update --help | grep -q "app"; then
    ok "pio update exposes app subcommand"
  else
    fail "pio update app subcommand missing"
  fi

  if pio update app --help >/dev/null; then
    ok "pio update app help"
  else
    fail "pio update app help failed"
  fi

  if pios update --help | grep -q "app"; then
    ok "pios update exposes app subcommand"
  else
    fail "pios update app subcommand missing"
  fi

  if pios update app --help >/dev/null; then
    ok "pios update app help"
  else
    fail "pios update app help failed"
  fi
}

check_repair_permissions_cli() {
  info "Checking repair CLI"

  if pio repair --help | grep -q ".pioreactor"; then
    ok "pio repair help"
  else
    fail "pio repair help failed"
    return
  fi

  local dot_pioreactor_root test_dir test_file status_before status_after
  dot_pioreactor_root="${DOT_PIOREACTOR:-$HOME/.pioreactor}"
  test_dir="$dot_pioreactor_root/agent_smoke_permissions_test"
  test_file="$test_dir/test.txt"

  mkdir -p "$test_dir"
  printf 'agent smoke permissions test\n' > "$test_file"

  chmod 0755 "$test_dir"
  chmod g-s "$test_dir"
  chmod 0644 "$test_file"

  if [[ -g "$test_dir" ]]; then
    fail "Unable to remove setgid bit from smoke test directory"
    rm -rf -- "$test_dir"
    return
  fi

  if status_before="$(pio status 2>/dev/null | grep 'storage:dot_pioreactor')"; then
    if echo "$status_before" | grep -Eq 'missing_group_write=[1-9][0-9]*' && \
       echo "$status_before" | grep -Eq 'missing_setgid_dirs=[1-9][0-9]*'; then
      ok "pio status detects intentionally broken .pioreactor permissions"
    else
      fail "pio status did not report intentionally broken .pioreactor permissions: $status_before"
    fi
  else
    fail "pio status did not report storage:dot_pioreactor"
  fi

  if sudo -n true >/dev/null 2>&1; then
    if pio repair >/dev/null; then
      ok "pio repair completed"
    else
      fail "pio repair failed"
      rm -rf -- "$test_dir"
      return
    fi
  else
    fail "passwordless sudo is required for pio repair"
    rm -rf -- "$test_dir"
    return
  fi

  if [[ -g "$test_dir" ]] && \
     find "$test_dir" -maxdepth 0 -perm -020 -print -quit | grep -q . && \
     find "$test_file" -maxdepth 0 -perm -020 -print -quit | grep -q .; then
    ok "pio repair restored group-write and setgid bits"
  else
    fail "pio repair did not restore expected permissions on smoke test files"
  fi

  if status_after="$(pio status 2>/dev/null | grep 'storage:dot_pioreactor')"; then
    if echo "$status_after" | grep -q 'missing_group_write=0' && \
       echo "$status_after" | grep -q 'missing_setgid_dirs=0'; then
      ok "pio status reports repaired .pioreactor permissions"
    else
      fail "pio status still reports .pioreactor permission drift after repair: $status_after"
    fi
  else
    fail "pio status did not report storage:dot_pioreactor after repair"
  fi

  rm -rf -- "$test_dir"
}

check_leader_api() {
  local hostname
  hostname="$(hostname)"

  run_step "Checking /api/workers" curl_check http://localhost/api/workers 'type=="array" and all(has("ipv4_address"))'
  run_step "Checking /api/units" curl_check http://localhost/api/units
  run_step "Checking /api/units/$hostname/capabilities" curl_check "http://localhost/api/units/$hostname/capabilities"
  run_step "Checking /api/units/$hostname/system/utc_clock" curl_check "http://localhost/api/units/$hostname/system/utc_clock"
  run_step "Checking /api/logs" curl_check http://localhost/api/logs
  run_step "Checking /api/local_access_point" curl_check http://localhost/api/local_access_point '.active | type=="boolean"'
}

check_time_series_endpoints() {
  local hostname experiment experiment_path source target_points=25 series_filter
  hostname="$(hostname)"

  info "Testing chart time series downsampling"
  if [[ "$HAS_JQ" != true ]]; then
    warn "jq not installed; skipping time series checks"
    return
  fi

  if ! experiment="$(get_assigned_experiment_via_api "$hostname")"; then
    fail "Unable to read the experiment assigned to $hostname"
    return
  fi
  if [[ -z "$experiment" ]]; then
    warn "$hostname is not assigned to an experiment; skipping time series checks"
    return
  fi
  experiment_path="$(uri_encode "$experiment")"

  # Each series holds at most target_points rows, in time order.
  series_filter=". as \$r | (\$r.series | type==\"array\") and (\$r.data | type==\"array\" and length==(\$r.series | length)) and all(\$r.data[]; length <= $target_points and ([.[].x] == ([.[].x] | sort)) and all(.[]; (.x | type==\"string\") and (.y | type==\"number\" or type==\"null\")))"

  for source in growth_rates temperature_readings od_readings_filtered od_readings od_readings_fused raw_od_readings; do
    run_step \
      "Checking /api/experiments/<experiment>/time_series/$source" \
      curl_check \
      "http://localhost/api/experiments/$experiment_path/time_series/$source?lookback=24&target_points=$target_points" \
      "$series_filter"
  done

  for source in growth_rates od_readings; do
    run_step \
      "Checking /api/workers/$hostname/experiments/<experiment>/time_series/$source" \
      curl_check \
      "http://localhost/api/workers/$hostname/experiments/$experiment_path/time_series/$source?lookback=24&target_points=$target_points" \
      "$series_filter"
  done

  run_step \
    "Checking time series rejects target_points=0" \
    http_status_is \
    400 \
    "http://localhost/api/experiments/$experiment_path/time_series/od_readings?target_points=0"
}


check_experiment_cli() {
  info "Testing pio experiments management CLI"
  local test_experiment
  test_experiment="smoke-test-$(date +%s)"

  if pio experiments create "$test_experiment" >/dev/null; then
    ok "created experiment $test_experiment"

    if pio experiments list | grep -q "$test_experiment"; then
      ok "experiment $test_experiment in list"
    else
      fail "experiment $test_experiment missing from list"
    fi

    if pio experiments delete "$test_experiment" --yes >/dev/null; then
      ok "deleted experiment $test_experiment"
    else
      fail "failed to delete experiment $test_experiment"
    fi
  else
    fail "pio experiments create failed"
    pio experiments delete "$test_experiment" >/dev/null || true
  fi
}

check_stirring_job() {
  info "Testing stirring job via API"
  if curl -fsS -X POST -H "Content-Type: application/json" -d '{}' http://localhost/unit_api/jobs/run/job_name/stirring >/dev/null; then
    ok "start stirring"
  else
    fail "start stirring failed"
    return
  fi

  info "Verifying stirring job is running"
  pause_for_job_sync
  local jobs_json
  if ! jobs_json="$(fetch_running_jobs)"; then
    fail "Unable to fetch running jobs"
    return
  fi

  if jobs_contain "$jobs_json" 'any(.job_name=="stirring")'; then
    ok "stirring job running"

    info "Checking stirring PWM duty cycle is non-zero"
    local duty_cycle
    if duty_cycle="$(read_pwm_duty_cycle)"; then
      if is_positive_number "$duty_cycle"; then
        ok "stirring PWM DC is ${duty_cycle}%"
      else
        fail "stirring PWM DC is ${duty_cycle:-unknown}"
      fi
    else
      fail "Unable to read stirring PWM duty cycle"
    fi

    check_pwm_channel_dc_topic "$jobs_json"
  else
    fail "stirring job not running"
  fi

  if jobs_contain "$jobs_json" 'any(.job_name=="mqtt_to_db_streaming")'; then
    ok "mqtt_to_db_streaming job running"
  else
    fail "mqtt_to_db_streaming job not running"
  fi

  sleep 5
  info "Stopping all jobs"
  if curl -fsS -X PATCH http://localhost/unit_api/jobs/stop/all >/dev/null; then
    ok "stopped all jobs"
  else
    fail "stop jobs failed"
  fi
}

check_pwm_channel_dc_topic() {
  local jobs_json="$1"
  local hostname experiment topic payload
  hostname="$(hostname)"

  mqtt_checks_available || return

  experiment="$(jq -r 'first(.[] | select(.job_name=="stirring") | .experiment) // empty' <<< "$jobs_json")"
  if [[ -z "$experiment" ]]; then
    fail "Unable to determine the stirring job's experiment"
    return
  fi

  topic="pioreactor/$hostname/$experiment/pwms/channel_dc"
  info "Checking retained PWM telemetry on $topic"
  if ! payload="$(mqtt_read_one "$topic")" || [[ -z "$payload" ]]; then
    fail "No retained message on $topic"
    return
  fi

  # Keyed by PWM channel (not GPIO pin) and timestamped by the worker.
  if jq -e '
    (.timestamp | type=="string" and length > 0)
    and (.channels | type=="object" and length > 0)
    and (.channels | keys | all(test("^[0-9]+$")))
    and (.channels | all(.[]; type=="number"))
    and (.channels | any(.[]; . > 0))
  ' <<< "$payload" >/dev/null; then
    ok "pwms/channel_dc publishes timestamped, channel-keyed duty cycles"
  else
    fail "pwms/channel_dc payload has an unexpected shape: $payload"
  fi
}

check_experiment_scoping() {
  info "Testing stop-all in experiment-specific way"
  if curl -fsS -X POST -H "Content-Type: application/json" -d '{"env":{"EXPERIMENT":"exp1"}}' http://localhost/unit_api/jobs/run/job_name/stirring >/dev/null; then
    ok "start stirring in exp1"
  else
    fail "start stirring exp1 failed"
  fi

  sleep 2

  if curl -fsS -X PATCH -H "Content-Type: application/json" -d '{"experiment":"exp2"}' http://localhost/unit_api/jobs/stop >/dev/null; then
    ok "stopped jobs in exp2"
  else
    fail "stop jobs exp2 failed"
  fi

  local jobs_json
  pause_for_job_sync
  if ! jobs_json="$(fetch_running_jobs)"; then
    fail "Unable to fetch running jobs"
    return
  fi

  if jobs_contain "$jobs_json" 'any(.experiment=="exp1") and all(.experiment!="exp2")'; then
    ok "exp1 job running, exp2 stopped"
  else
    fail "exp-specific stop-all failed"
  fi
}

check_experiment_profiles() {
  info "Testing new experiment_profiles appear in API"
  mkdir -p ~/.pioreactor/experiment_profiles
  cat <<'YAML' > ~/.pioreactor/experiment_profiles/test_profile.yaml
version: "1.0"
experiment_profile_name: test_profile
YAML

  if http_json_ok http://localhost/api/experiment_profiles '.[] | select(.experimentProfile.experiment_profile_name == "test_profile")'; then
    ok "test_profile in experiment_profiles"
  else
    fail "test_profile not in experiment_profiles"
  fi

  rm -f ~/.pioreactor/experiment_profiles/test_profile.yaml
}

check_experiment_profile_validation() {
  info "Testing experiment profile validation diagnostics"

  if ! python3_available; then
    warn "python3 not available; skipping experiment profile validation diagnostics"
    return
  fi

  local payload_file response_file status
  payload_file="$(mktemp)"
  response_file="$(mktemp)"

  python3 > "$payload_file" <<'PY'
import json

body = """\
version: "1.0"
experiment_profile_name: agent_smoke_invalid_expression
common:
  jobs:
    stirring:
      actions:
        - type: start
          t: 0s
          if: 1 +
"""

print(json.dumps({"filename": "agent_smoke_invalid_expression.yaml", "body": body}))
PY

  status="$(curl -sS -o "$response_file" -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d "@$payload_file" \
    http://localhost/api/experiment_profiles)"

  if [[ "$status" == "400" ]]; then
    ok "invalid expression profile rejected"
  else
    fail "invalid expression profile returned HTTP $status"
    print_prefixed_file_excerpt "profile validation response: " "$response_file" 2000
    rm -f "$payload_file" "$response_file"
    return
  fi

  if [[ "$HAS_JQ" == true ]]; then
    if jq -e \
      '.error=="Validation error." and any(.diagnostics[]?; .code=="expression.syntax" and .path=="common.jobs.stirring.actions[0].if")' \
      "$response_file" >/dev/null; then
      ok "profile validation returned expression.syntax diagnostic"
    else
      fail "profile validation response missing expected diagnostic"
      print_prefixed_file_excerpt "profile validation response: " "$response_file" 2000
    fi
  else
    ok "profile validation returned HTTP 400"
  fi

  rm -f "$payload_file" "$response_file"
}

check_exportable_datasets_listing() {
  info "Testing new exportable_datasets appear in API"
  mkdir -p ~/.pioreactor/exportable_datasets
  cat <<'YAML' > ~/.pioreactor/exportable_datasets/test_dataset.yaml
dataset_name: test_dataset
description: "Smoke test dataset"
display_name: "Test Dataset"
has_experiment: false
has_unit: false
timestamp_columns: ["created_at"]
default_order_by: "created_at"
source: "app"
YAML

  if http_json_ok http://localhost/api/datasets/exportable '.[] | select(.dataset_name=="test_dataset")'; then
    ok "test_dataset listed"
  else
    fail "test_dataset not listed"
  fi

  rm -f ~/.pioreactor/exportable_datasets/test_dataset.yaml
}

check_exportable_dataset_preview_validation() {
  info "Testing exportable dataset preview row limit validation"
  mkdir -p ~/.pioreactor/exportable_datasets
  cat <<'YAML' > ~/.pioreactor/exportable_datasets/agent_smoke_preview_dataset.yaml
dataset_name: agent_smoke_preview_dataset
description: "Smoke test preview dataset"
display_name: "Agent Smoke Preview Dataset"
has_experiment: false
has_unit: false
timestamp_columns: []
default_order_by: null
query: "SELECT 1 AS value"
source: "app"
YAML

  if http_json_ok http://localhost/api/datasets/exportable/agent_smoke_preview_dataset/preview?n_rows=2 'type=="array"'; then
    ok "preview accepts valid n_rows"
  else
    fail "preview rejected valid n_rows"
  fi

  if http_status_is 400 "http://localhost/api/datasets/exportable/agent_smoke_preview_dataset/preview?n_rows=101"; then
    ok "preview rejects n_rows above limit"
  else
    fail "preview did not reject n_rows above limit"
  fi

  if http_status_is 400 "http://localhost/api/datasets/exportable/agent_smoke_preview_dataset/preview?n_rows=not-an-int"; then
    ok "preview rejects non-integer n_rows"
  else
    fail "preview did not reject non-integer n_rows"
  fi

  rm -f ~/.pioreactor/exportable_datasets/agent_smoke_preview_dataset.yaml
}

check_export_datasets_endpoint() {
  info "Testing export_datasets endpoint"

  local export_experiment payload
  export_experiment="agent-smoke-export"
  payload='{"datasets":["experiments","liquid_volumes"],"experiment":"agent-smoke-export","partition_by_unit":false,"partition_by_experiment":false}'
  local response

  if ! response="$(curl -fsS -X POST -H "Content-Type: application/json" -d "$payload" http://localhost/api/datasets/exportable/export)"; then
    fail "export_datasets request failed"
    return
  fi

  if [[ "$HAS_JQ" == true ]]; then
    if echo "$response" | jq -e '.status=="accepted"' >/dev/null; then
      ok "export_datasets task accepted"
    else
      fail "export_datasets response did not report accepted status"
      return
    fi

    local result_url_path
    result_url_path="$(echo "$response" | jq -r '.result_url_path // empty')"
    if [[ -z "$result_url_path" ]]; then
      local msg
      msg="$(echo "$response" | jq -r '.error // .msg // "missing result_url_path"')"
      fail "export_datasets request failed: $msg"
      return
    fi

    local task_response=""
    local task_status=""
    local task_completed=false
    for _ in {1..120}; do
      if ! task_response="$(curl -fsS "http://localhost${result_url_path}")"; then
        fail "export_datasets task poll failed"
        return
      fi

      task_status="$(echo "$task_response" | jq -r '.status // empty')"
      if [[ "$task_status" == "succeeded" || "$task_status" == "failed" ]]; then
        task_completed=true
        break
      fi

      sleep 0.5
    done

    if [[ "$task_completed" != true ]]; then
      fail "export_datasets timed out waiting for task completion (last status: ${task_status:-unknown})"
      return
    fi

    if [[ "$task_status" != "succeeded" ]]; then
      local msg
      msg="$(echo "$task_response" | jq -r '.error // .msg // "unknown error"')"
      fail "export_datasets failed: $msg"
      return
    fi

    if echo "$task_response" | jq -e '.result.result == true' >/dev/null; then
      local filename archive_file
      filename="$(echo "$task_response" | jq -r '.result.filename // empty')"
      if [[ -z "$filename" ]]; then
        fail "export_datasets succeeded without a filename"
        return
      fi

      ok "export_datasets succeeded (file: $filename)"
      archive_file="/run/pioreactor/exports/$filename"
      if [[ ! -f "$archive_file" ]]; then
        fail "export file not found: $archive_file"
        return
      fi
      ok "export file present: $archive_file"

      if python3_available; then
        if python3 - "$archive_file" "$export_experiment" <<'PY'
import json
import sys
import zipfile

archive_path, experiment = sys.argv[1:]
datasets = ["experiments", "liquid_volumes"]

with zipfile.ZipFile(archive_path) as archive:
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["schema_version"] == 1
    assert manifest["filters"]["experiment"] == experiment
    assert manifest["selected_datasets"] == datasets

    for dataset in datasets:
        schema = json.loads(archive.read(f"{dataset}/schema.json"))
        assert schema["schema_version"] == 1
        assert schema["dataset_name"] == dataset
PY
        then
          ok "export archive contains versioned manifest and dataset metadata"
        else
          fail "export archive metadata is invalid"
        fi
      else
        warn "python3 not available; skipping export archive metadata validation"
      fi
    else
      local msg
      msg="$(echo "$task_response" | jq -r '.result.msg // .msg // "unknown error"')"
      fail "export_datasets failed: $msg"
    fi
  else
    ok "export_datasets task accepted"
  fi
}

check_dropin_plugin_discovery() {
  info "Testing drop-in plugin script discovery"
  mkdir -p ~/.pioreactor/plugins
  cat <<'PY' > ~/.pioreactor/plugins/pioreactor_test_plugin.py
# dummy drop-in plugin script for smoke test
def dummy_plugin():
    return None
PY

  if pio plugins list | grep -q pioreactor_test_plugin; then
    ok "drop-in plugin pioreactor_test_plugin discovered"
  else
    fail "drop-in plugin pioreactor_test_plugin not discovered"
  fi

  rm -f ~/.pioreactor/plugins/pioreactor_test_plugin.py
}

check_calibration_discovery() {
  info "Testing custom calibration discovery via struct"
  mkdir -p ~/.pioreactor/storage/calibrations/od/
  cat <<EOF > ~/.pioreactor/storage/calibrations/od/my_test_cal.yaml
calibration_name: my_test_cal
calibration_type: od
calibrated_on_pioreactor_unit: "$(hostname)"
created_at: 2025-01-01 21:45:48.937062+00:00
ir_led_intensity: 50
angle: "90"
pd_channel: "1"
curve_data_:
  type: poly
  coefficients:
    - 1.0
x: "OD"
y: "Voltage"
recorded_data:
  x: []
  y: []
EOF

  if http_json_ok http://localhost/unit_api/calibrations/od '.[] | select(.calibration_name=="my_test_cal")'; then
    ok "my_test_cal in calibrations list"
  else
    fail "my_test_cal not in calibrations list"
  fi

  if http_json_ok http://localhost/unit_api/calibrations/od/my_test_cal '.calibration_name=="my_test_cal"'; then
    ok "detail endpoint for my_test_cal succeeded"
  else
    fail "detail endpoint for my_test_cal failed"
  fi

  rm -f ~/.pioreactor/storage/calibrations/od/my_test_cal.yaml
}

check_storage_path_validation() {
  info "Testing storage path validation"

  run_step \
    "Checking calibration route rejects invalid device path" \
    http_status_is \
    400 \
    http://localhost/unit_api/calibrations/bad:name

  run_step \
    "Checking estimator route rejects invalid device path" \
    http_status_is \
    400 \
    http://localhost/unit_api/estimators/bad:name

  local dot_pioreactor_root outside_file symlink_path symlink_name
  dot_pioreactor_root="${DOT_PIOREACTOR:-$HOME/.pioreactor}"
  symlink_name="agent_smoke_outside_link"
  symlink_path="$dot_pioreactor_root/$symlink_name"

  if [[ -e "$symlink_path" || -L "$symlink_path" ]]; then
    warn "$symlink_path already exists; skipping symlink escape check"
    return
  fi

  outside_file="$(mktemp)"
  printf 'agent smoke path validation\n' > "$outside_file"
  ln -s "$outside_file" "$symlink_path"

  run_step \
    "Checking /unit_api/system/path rejects symlink outside DOT_PIOREACTOR" \
    http_status_is \
    403 \
    "http://localhost/unit_api/system/path/$symlink_name"

  rm -f "$symlink_path" "$outside_file"
}

check_broadcast_endpoints() {
  info "Testing broadcast endpoints"
  local broadcast_literal='$broadcast'
  run_step "Checking /api/units/${broadcast_literal}/system/utc_clock" curl_check "http://localhost/api/units/\$broadcast/system/utc_clock"

  local jobs_map
  if jobs_map="$(curl -fsS "http://localhost/api/workers/\$broadcast/jobs/running")"; then
    if [[ "$HAS_JQ" == true ]]; then
      if echo "$jobs_map" | jq -e 'type=="object"' >/dev/null; then
        ok "/api/workers/${broadcast_literal}/jobs/running returns mapping"
      else
        fail "/api/workers/${broadcast_literal}/jobs/running did not return a mapping"
      fi
    else
      ok "Received broadcast jobs data"
    fi
  else
    fail "/api/workers/${broadcast_literal}/jobs/running failed"
  fi
}

check_numpy_installation() {
  info "Testing numpy install"
  if python -c "import numpy" >/dev/null 2>&1; then
    ok "numpy installed correctly"
  else
    fail "numpy not installed correctly"
  fi
}

check_thermostat_job() {
  info "Testing thermostat job via API"
  if curl -fsS -X POST -H "Content-Type: application/json" -d '{"options": {"automation_name": "thermostat", "target_temperature": 30}}' http://localhost/unit_api/jobs/run/job_name/temperature_automation >/dev/null; then
    ok "start thermostat"
  else
    fail "start thermostat failed"
    return
  fi

  info "Verifying thermostat job is running"
  pause_for_job_sync
  local jobs_json
  if ! jobs_json="$(fetch_running_jobs)"; then
    fail "Unable to fetch running jobs"
    return
  fi

  if jobs_contain "$jobs_json" 'any(.job_name=="temperature_automation")'; then
    ok "thermostat job running"
  else
    fail "thermostat job not running"
  fi

  sleep 5
  info "Stopping all jobs"
  if curl -fsS -X PATCH http://localhost/unit_api/jobs/stop/all >/dev/null; then
    ok "stopped all jobs"
  else
    fail "stop jobs failed"
  fi
}

check_pump_actions() {
  info "Testing pump actions via pio commands"
  local actions=(add_media add_alt_media remove_waste circulate_media circulate_alt_media)

  for action in "${actions[@]}"; do
    if pio run "$action" --duration 1 >/dev/null; then
      ok "pio run $action --duration 1"
    else
      fail "pio run $action --duration 1 failed"
    fi
  done
}

check_bioreactor_topic_payloads() {
  local hostname experiment variable topic payload
  hostname="$(hostname)"

  info "Checking retained bioreactor values are timestamped"
  mqtt_checks_available || return

  if ! experiment="$(get_assigned_experiment_via_api "$hostname")"; then
    fail "Unable to read the experiment assigned to $hostname"
    return
  fi
  if [[ -z "$experiment" ]]; then
    warn "$hostname is not assigned to an experiment; skipping bioreactor topic checks"
    return
  fi

  for variable in current_volume_ml alt_media_fraction; do
    topic="pioreactor/$hostname/$experiment/bioreactor/$variable"
    if ! payload="$(mqtt_read_one "$topic" 3)" || [[ -z "$payload" ]]; then
      warn "No retained value on $topic"
      continue
    fi

    if jq -e '(.timestamp | type=="string" and length > 0) and (.value | type=="number")' \
      <<< "$payload" >/dev/null 2>&1; then
      ok "$variable publishes {timestamp, value}"
    else
      fail "$topic payload is not {timestamp, value}: $payload"
    fi
  done
}

check_plugin_install_cycle() {
  # This distribution intentionally keeps its assets under the differently named
  # `oled_status_display` entry-point package.
  local plugin_name="pioreactor-oled-status-display-plugin"
  local descriptor_file="$HOME/.pioreactor/plugins/ui/jobs/oled_status_display.yaml"
  local installed_by_smoke_test=false

  info "Testing packaged plugin asset install cycle with $plugin_name"
  if pio plugins list | grep -Eq 'pioreactor[-_]oled[-_]status[-_]display[-_]plugin'; then
    warn "$plugin_name was already installed; it will be left installed"
  elif pio plugins install "$plugin_name" >/dev/null; then
    installed_by_smoke_test=true
    ok "installed $plugin_name"
  else
    fail "$plugin_name install failed"
    return
  fi

  if pio plugins list | grep -Eq 'pioreactor[-_]oled[-_]status[-_]display[-_]plugin'; then
    ok "$plugin_name listed"
  else
    fail "$plugin_name not listed after install"
  fi

  if [[ -s "$descriptor_file" ]] && grep -q '^job_name: oled_status_display$' "$descriptor_file"; then
    ok "$plugin_name UI descriptor installed from its entry-point package"
  else
    fail "$plugin_name UI descriptor was not installed"
  fi

  if crudini --get \
    "$HOME/.pioreactor/unit_config.ini" \
    oled_status_display.config \
    refresh_interval_seconds \
    >/dev/null 2>&1; then
    ok "$plugin_name additional config installed from its entry-point package"
  else
    fail "$plugin_name additional config was not installed"
  fi

  if http_json_ok \
    http://localhost/unit_api/jobs/descriptors \
    'type=="array" and any(.job_name=="oled_status_display")'; then
    ok "$plugin_name descriptor is available through the unit API"
  else
    fail "$plugin_name descriptor is missing from the unit API"
  fi

  if [[ "$installed_by_smoke_test" == true ]]; then
    if pio plugins uninstall "$plugin_name" >/dev/null; then
      ok "uninstalled $plugin_name"
    else
      fail "$plugin_name uninstall failed"
      return
    fi

    if pio plugins list | grep -Eq 'pioreactor[-_]oled[-_]status[-_]display[-_]plugin'; then
      fail "$plugin_name still listed after uninstall"
    else
      ok "$plugin_name absent from plugin list after uninstall"
    fi

    if [[ -e "$descriptor_file" ]]; then
      fail "$plugin_name UI descriptor remains after uninstall"
    else
      ok "$plugin_name UI descriptor removed before package uninstall"
    fi
  fi
}

check_pios_cli() {
  info "Testing pios CLI"
  if pios run stirring -y >/dev/null; then
    ok "pios run stirring"
  else
    fail "pios run stirring failed"
  fi

  sleep 5

  if pios kill --job-name stirring -y >/dev/null; then
    ok "pios kill stirring"
  else
    fail "pios kill stirring failed"
  fi
}

check_pios_cp_target_help() {
  info "Checking pios cp target argument"
  if pios cp --help | grep -q "TARGET"; then
    ok "pios cp exposes optional TARGET argument"
  else
    fail "pios cp optional TARGET argument missing"
  fi
}

check_pios_sync_configs() {
  info "Testing pios sync-configs"
  if pios sync-configs >/dev/null; then
    ok "pios sync-configs"
  else
    fail "pios sync-configs failed"
  fi
}

restore_available_worker_inventory_via_api() {
  local worker="$1"
  local is_active="$2"
  local model_name="$3"
  local model_version="$4"
  local payload_file active_payload_file
  payload_file="$(mktemp)"
  active_payload_file="$(mktemp)"

  python3 - "$worker" "$model_name" "$model_version" > "$payload_file" <<'PY'
import json
import sys

worker = sys.argv[1]
model_name = sys.argv[2] or None
model_version = sys.argv[3] or None
print(json.dumps({"pioreactor_unit": worker, "model_name": model_name, "model_version": model_version}))
PY

  python3 - "$is_active" > "$active_payload_file" <<'PY'
import json
import sys

print(json.dumps({"is_active": int(sys.argv[1])}))
PY

  curl -fsS -X PUT -H "Content-Type: application/json" -d "@$payload_file" http://localhost/api/workers >/dev/null && \
    curl -fsS -X PUT -H "Content-Type: application/json" -d "@$active_payload_file" "http://localhost/api/workers/$worker/is_active" >/dev/null
  local status=$?
  rm -f "$payload_file" "$active_payload_file"
  return "$status"
}

check_available_worker_remove_add() {
  local worker="$AVAILABLE_WORKER_NAME"
  local address="$AVAILABLE_WORKER_ADDRESS"
  local model_name="$AVAILABLE_WORKER_MODEL_NAME"
  local model_version="$AVAILABLE_WORKER_MODEL_VERSION"
  local add_args=(pio workers add "$worker" --address "$address")

  if [[ -n "$model_name" && -n "$model_version" ]]; then
    add_args+=(--model-name "$model_name" --model-version "$model_version")
  fi

  info "Testing worker inventory remove/add cycle for $worker"
  if pio workers remove "$worker" >/dev/null; then
    ok "removed worker $worker from inventory"
  else
    fail "failed to remove worker $worker from inventory"
    return
  fi

  if worker_inventory_contains "$worker"; then
    fail "worker $worker still present after removal"
  else
    ok "worker $worker absent after removal"
  fi

  if "${add_args[@]}" >/dev/null; then
    ok "added worker $worker back with pio workers add"
  else
    fail "pio workers add failed for $worker; attempting API inventory restore"
    if restore_available_worker_inventory_via_api "$worker" "$AVAILABLE_WORKER_IS_ACTIVE" "$model_name" "$model_version"; then
      ok "restored worker $worker inventory row via API"
    else
      fail "failed to restore worker $worker inventory row via API"
    fi
    return
  fi

  if [[ "$AVAILABLE_WORKER_IS_ACTIVE" != "1" ]]; then
    if pio workers update-active "$worker" "$AVAILABLE_WORKER_IS_ACTIVE" >/dev/null; then
      ok "restored worker $worker active state"
    else
      fail "failed to restore worker $worker active state"
    fi
  fi

  if worker_inventory_contains "$worker"; then
    ok "worker $worker present after add-back"
  else
    fail "worker $worker missing after add-back"
  fi

  check_available_worker_model_after_add
}

check_available_worker_plugin_install() {
  local worker="$AVAILABLE_WORKER_NAME"
  local base_url="$1"
  local plugin_name="pioreactor_air_bubbler"
  local already_installed=false
  local dispatch_response_file task_result_file uninstall_response_file uninstall_result_file
  dispatch_response_file="$(mktemp)"
  task_result_file="$(mktemp)"

  info "Testing plugin install on worker $worker"
  if worker_plugin_list_contains "$base_url" "$plugin_name"; then
    already_installed=true
    ok "$plugin_name already installed on $worker"
  fi

  if curl -fsS \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{"args":["pioreactor_air_bubbler"],"options":{}}' \
    "$base_url/unit_api/plugins/install" > "$dispatch_response_file"; then
    ok "dispatched $plugin_name install to $worker"
  else
    fail "failed to dispatch $plugin_name install to $worker"
    print_prefixed_file_excerpt "install response: " "$dispatch_response_file" 2000
    rm -f "$dispatch_response_file" "$task_result_file"
    return
  fi

  if ! wait_for_worker_task_success "$base_url" "$dispatch_response_file" "$task_result_file" "$plugin_name install" 300 2 15; then
    warn "$plugin_name install task result:"
    print_prefixed_file_excerpt "  " "$task_result_file" 4000
    write_worker_plugin_install_diagnostics "$worker" "$base_url" "$plugin_name" "$dispatch_response_file"
    rm -f "$dispatch_response_file" "$task_result_file"
    return
  fi

  if wait_for_worker_plugin "$base_url" "$plugin_name"; then
    ok "$plugin_name installed on $worker"
  else
    fail "$plugin_name did not appear in worker plugin list"
    write_worker_plugin_install_diagnostics "$worker" "$base_url" "$plugin_name" "$dispatch_response_file"
    rm -f "$dispatch_response_file" "$task_result_file"
    return
  fi

  rm -f "$dispatch_response_file" "$task_result_file"

  if [[ "$already_installed" == false ]]; then
    uninstall_response_file="$(mktemp)"
    uninstall_result_file="$(mktemp)"
    if curl -fsS \
      -X POST \
      -H "Content-Type: application/json" \
      -d '{"args":["pioreactor_air_bubbler"],"options":{}}' \
      "$base_url/unit_api/plugins/uninstall" > "$uninstall_response_file"; then
      ok "dispatched $plugin_name uninstall from $worker"
      if ! wait_for_worker_task_success "$base_url" "$uninstall_response_file" "$uninstall_result_file" "$plugin_name uninstall"; then
        warn "$plugin_name uninstall task result:"
        print_prefixed_file_excerpt "  " "$uninstall_result_file" 4000
      fi
      if wait_for_worker_plugin_absent "$base_url" "$plugin_name"; then
        ok "$plugin_name uninstalled from $worker"
      else
        fail "$plugin_name still appears in worker plugin list after uninstall"
      fi
    else
      fail "failed to dispatch $plugin_name uninstall from $worker"
      print_prefixed_file_excerpt "uninstall response: " "$uninstall_response_file" 2000
    fi
    rm -f "$uninstall_response_file" "$uninstall_result_file"
  else
    warn "$plugin_name was already installed on $worker; leaving it installed"
  fi
}

check_available_worker_pios_cp() {
  local worker="$AVAILABLE_WORKER_NAME"
  local base_url="$1"
  local token="$2"
  local local_file remote_file remote_path worker_dot_pioreactor

  local_file="$(mktemp)"
  remote_file="agent_smoke_cp_${token}.py"

  if ! worker_dot_pioreactor="$(get_worker_dot_pioreactor_root "$base_url")"; then
    fail "failed to resolve DOT_PIOREACTOR on $worker"
    rm -f "$local_file"
    return
  fi
  remote_path="$worker_dot_pioreactor/plugins/$remote_file"

  cat > "$local_file" <<'PY'
# agent smoke cluster copy probe
AGENT_SMOKE_CLUSTER_COPY = True
PY
  chmod 0644 "$local_file"

  info "Testing pios cp to worker $worker"
  if pios cp "$local_file" "$remote_path" --units "$worker" -y >/dev/null; then
    ok "pios cp copied probe file to $worker"
  else
    fail "pios cp failed for $worker"
    rm -f "$local_file"
    return
  fi

  if curl -fsS "$base_url/unit_api/system/path/plugins/$remote_file" | grep -q "AGENT_SMOKE_CLUSTER_COPY"; then
    ok "copied probe file is readable on $worker"
  else
    fail "copied probe file not readable on $worker"
  fi

  if pios rm "$remote_path" --units "$worker" -y >/dev/null; then
    ok "removed copied probe file from $worker"
  else
    fail "failed to remove copied probe file from $worker"
  fi

  rm -f "$local_file"
}

check_available_worker_config_edit() {
  local worker="$AVAILABLE_WORKER_NAME"
  local token="$1"
  local original_config modified_config section_name
  original_config="$(mktemp)"
  modified_config="$(mktemp)"
  section_name="agent.smoke_test_${token}"

  info "Testing worker-specific config edit for $worker"
  if ! curl -fsS "http://localhost/api/config/units/$worker/specific" > "$original_config"; then
    fail "failed to fetch unit-specific config for $worker"
    rm -f "$original_config" "$modified_config"
    return
  fi

  if ! append_config_smoke_section "$original_config" "$modified_config" "$section_name" "$worker"; then
    fail "failed to prepare config edit for $worker"
    rm -f "$original_config" "$modified_config"
    return
  fi

  if patch_unit_specific_config "$worker" "$modified_config"; then
    ok "patched unit-specific config on $worker"
  else
    fail "failed to patch unit-specific config on $worker"
    patch_unit_specific_config "$worker" "$original_config" >/dev/null || true
    rm -f "$original_config" "$modified_config"
    return
  fi

  if worker_specific_config_has_section "$worker" "$section_name"; then
    ok "merged config includes smoke section for $worker"
  else
    fail "merged config missing smoke section for $worker"
  fi

  if patch_unit_specific_config "$worker" "$original_config"; then
    ok "restored unit-specific config on $worker"
  else
    fail "failed to restore unit-specific config on $worker"
  fi

  if pios sync-configs --specific --skip-save --units "$worker" >/dev/null; then
    ok "pios sync-configs --specific for $worker"
  else
    fail "pios sync-configs --specific failed for $worker"
  fi

  rm -f "$original_config" "$modified_config"
}

check_available_worker_job_cycle() {
  local worker="$AVAILABLE_WORKER_NAME"
  local base_url="$1"
  local current_experiment smoke_experiment created_smoke_experiment=false

  if ! current_experiment="$(get_worker_experiment_assignment "$worker")"; then
    fail "failed to read experiment assignment for $worker"
    return
  fi

  if [[ -z "$current_experiment" ]]; then
    smoke_experiment="agent-smoke-$(date +%s)"
    info "Assigning $worker to temporary experiment $smoke_experiment for stirring test"
    if ! pio experiments create "$smoke_experiment" >/dev/null; then
      fail "failed to create temporary experiment $smoke_experiment"
      return
    fi

    if pio workers assign "$worker" "$smoke_experiment" >/dev/null; then
      ok "assigned $worker to temporary experiment $smoke_experiment"
      created_smoke_experiment=true
    else
      fail "failed to assign $worker to temporary experiment $smoke_experiment"
      pio experiments delete "$smoke_experiment" --yes >/dev/null || true
      return
    fi
  else
    ok "$worker is assigned to experiment $current_experiment"
  fi

  info "Testing targeted pios job cycle on worker $worker"
  if pios run stirring --units "$worker" -y >/dev/null; then
    ok "pios run stirring on $worker"
  else
    fail "pios run stirring failed on $worker"
    if [[ "$created_smoke_experiment" == true ]]; then
      restore_temporary_worker_experiment_assignment "$worker" "$smoke_experiment"
    fi
    return
  fi

  pause_for_job_sync
  if worker_running_jobs_contain "$base_url" stirring; then
    ok "stirring running on $worker"
  else
    fail "stirring not reported as running on $worker"
  fi

  if pios jobs list running --units "$worker" >/dev/null; then
    ok "pios jobs list running for $worker"
  else
    fail "pios jobs list running failed for $worker"
  fi

  if pios kill --job-name stirring --units "$worker" -y >/dev/null; then
    ok "pios kill stirring on $worker"
  else
    fail "pios kill stirring failed on $worker"
  fi

  pause_for_job_sync
  if worker_running_jobs_contain "$base_url" stirring; then
    fail "stirring still reported as running on $worker after kill"
  else
    ok "stirring stopped on $worker"
  fi

  if [[ "$created_smoke_experiment" == true ]]; then
    restore_temporary_worker_experiment_assignment "$worker" "$smoke_experiment"
  fi
}

check_available_worker_identity() {
  local worker="$AVAILABLE_WORKER_NAME"
  local base_url="$1"
  local leader clock_json synchronized worker_model model_name model_version capacity
  leader="$(hostname)"

  info "Testing clock, model, and request guards on worker $worker"
  if [[ "$HAS_JQ" != true ]]; then
    warn "jq not installed; skipping worker identity checks"
    return
  fi

  if clock_json="$(curl -fsS --max-time 5 "$base_url/unit_api/system/utc_clock")"; then
    synchronized="$(jq -r 'if has("synchronized") then (.synchronized | tostring) else "missing" end' <<< "$clock_json")"
    case "$synchronized" in
      true)
        ok "$worker clock is synchronised"
        ;;
      false)
        fail "$worker clock is not synchronised; measurement timestamps may be wrong"
        ;;
      null)
        warn "$worker clock synchronisation state is unknown"
        ;;
      *)
        fail "$worker /unit_api/system/utc_clock is missing 'synchronized'"
        ;;
    esac
  else
    fail "unable to read $worker /unit_api/system/utc_clock"
  fi

  if worker_model="$(curl -fsS --max-time 5 "$base_url/unit_api/model")" && \
     jq -e '(.model_name | type=="string") and (.model_version | type=="string") and (.reactor_capacity_ml | type=="number")' \
       <<< "$worker_model" >/dev/null; then
    model_name="$(jq -r '.model_name' <<< "$worker_model")"
    model_version="$(jq -r '.model_version' <<< "$worker_model")"
    capacity="$(jq -r '.reactor_capacity_ml' <<< "$worker_model")"
    ok "$worker saved its own model: $model_name v$model_version"

    # The leader reads the definition from the worker, so worker-only models work too.
    run_step \
      "Checking leader's /api/workers/$worker/model matches the worker's definition" \
      curl_check \
      "http://localhost/api/workers/$worker/model" \
      ".model_name==\"$model_name\" and .model_version==\"$model_version\" and .reactor_capacity_ml==$capacity"
    run_step \
      "Checking leader inventory mirrors $worker's model" \
      curl_check \
      http://localhost/api/workers \
      "any(.[]; .pioreactor_unit==\"$worker\" and .model_name==\"$model_name\" and .model_version==\"$model_version\")"
  else
    fail "$worker has no saved model at /unit_api/model; set it with: pio model set <name> <version> on $worker"
  fi

  run_step \
    "Checking $worker rejects writes addressed to $leader" \
    http_status_is \
    409 \
    "$base_url/unit_api/jobs/stop" \
    -X PATCH \
    -H "Content-Type: application/json" \
    -H "X-Pioreactor-Target: $leader" \
    -d "$NOOP_STOP_PAYLOAD"
  run_step \
    "Checking $worker accepts writes addressed to itself" \
    http_status_is \
    202 \
    "$base_url/unit_api/jobs/stop" \
    -X PATCH \
    -H "Content-Type: application/json" \
    -H "X-Pioreactor-Target: $worker" \
    -d "$NOOP_STOP_PAYLOAD"

  # Workers don't consult the inventory: only their own pages and localhost may write.
  run_step \
    "Checking $worker rejects browser writes from another Pioreactor's page" \
    http_status_is \
    403 \
    "$base_url/unit_api/jobs/stop" \
    -X PATCH \
    -H "Content-Type: application/json" \
    -H "Origin: http://$leader.local" \
    -d "$NOOP_STOP_PAYLOAD"
  run_step \
    "Checking $worker accepts browser writes from its own page" \
    http_status_is \
    202 \
    "$base_url/unit_api/jobs/stop" \
    -X PATCH \
    -H "Content-Type: application/json" \
    -H "Origin: $base_url" \
    -d "$NOOP_STOP_PAYLOAD"
}

check_available_worker_packaging() {
  local worker="$AVAILABLE_WORKER_NAME"
  local host="${AVAILABLE_WORKER_ADDRESS#http://}"
  host="${host#https://}"
  local -a ssh_cmd=(ssh -o BatchMode=yes -o ConnectTimeout=5 "pioreactor@$host")

  info "Testing runtime packaging on worker $worker over SSH"
  if ! "${ssh_cmd[@]}" true >/dev/null 2>&1; then
    warn "SSH to $worker unavailable; skipping worker packaging checks"
    return
  fi

  if "${ssh_cmd[@]}" 'test -x /usr/sbin/mosquitto && command -v mosquitto_sub >/dev/null && command -v mosquitto_pub >/dev/null'; then
    ok "$worker has the mosquitto broker and clients installed"
  else
    fail "$worker is missing mosquitto packages"
  fi

  if "${ssh_cmd[@]}" 'systemctl is-active --quiet mosquitto'; then
    fail "mosquitto broker is running on non-leader worker $worker"
  else
    ok "mosquitto broker is not running on $worker"
  fi

  if "${ssh_cmd[@]}" 'grep -Eq "huey_consumer.*[[:space:]]-w[[:space:]]+1([[:space:]]|$)" /usr/local/bin/start_pioreactor_huey.sh'; then
    fail "$worker Huey launcher starts a single worker"
  else
    ok "$worker Huey launcher starts at least two workers"
  fi

  # Set by the worker's own experiment lookups, e.g. during the job cycle above.
  # shellcheck disable=SC2016 # Expanded on the worker.
  if "${ssh_cmd[@]}" 'source /etc/pioreactor.env 2>/dev/null; "${PIO_VENV:-/opt/pioreactor/venv}/bin/pio" cache list' | \
    grep -qx cluster_membership; then
    ok "$worker caches its last known cluster membership"
  else
    fail "$worker has no cluster_membership cache"
  fi
}

check_available_worker_model_after_add() {
  local worker="$AVAILABLE_WORKER_NAME"
  local model_name="$AVAILABLE_WORKER_MODEL_NAME"
  local model_version="$AVAILABLE_WORKER_MODEL_VERSION"
  local base_url

  if [[ "$HAS_JQ" != true || -z "$model_name" || -z "$model_version" ]]; then
    return
  fi

  # Adding a worker saves its model on the worker and reboots it.
  wait_for_available_worker_api "$worker" || return
  base_url="$(worker_base_url "$AVAILABLE_WORKER_ADDRESS")"

  run_step \
    "Checking $worker kept model $model_name v$model_version across add-back and reboot" \
    curl_check \
    "$base_url/unit_api/model" \
    ".model_name==\"$model_name\" and .model_version==\"$model_version\""
  run_step \
    "Checking leader inventory has $worker's model after add-back" \
    curl_check \
    http://localhost/api/workers \
    "any(.[]; .pioreactor_unit==\"$worker\" and .model_name==\"$model_name\" and .model_version==\"$model_version\")"
}

check_available_worker_cluster_branch() {
  info "Checking for an available non-leader worker"
  if ! select_available_worker; then
    return
  fi

  local worker base_url token
  worker="$AVAILABLE_WORKER_NAME"
  base_url="$(worker_base_url "$AVAILABLE_WORKER_ADDRESS")"
  token="$(date +%s)"

  ok "Using available worker $worker at $AVAILABLE_WORKER_ADDRESS"
  run_step "Checking targeted worker clock through leader API" curl_check "http://localhost/api/units/$worker/system/utc_clock"
  run_step "Checking targeted worker plugins route through leader API" curl_check "http://localhost/api/units/$worker/plugins/installed"

  check_available_worker_identity "$base_url"
  check_available_worker_plugin_install "$base_url"
  check_available_worker_pios_cp "$base_url" "$token"
  check_available_worker_config_edit "$token"
  check_available_worker_job_cycle "$base_url"
  check_available_worker_packaging
  check_available_worker_remove_add
}

summarize() {
  if (( FAILURE_COUNT > 0 )); then
    printf "${RED}[summary] %d failure(s) detected${NC}\n" "$FAILURE_COUNT"
    exit 1
  fi

  ok "Production smoke test completed"
}

main() {
  parse_args "$@"
  shift $((OPTIND - 1))

  ensure_not_root
  enter_pioreactor_home
  detect_optional_tools
  require_cmd pio curl pios crudini

  info "Host: $(hostname)  IP: $(hostname -I || true)"

  run_tests

  cleanup
  summarize
}

main "$@"
