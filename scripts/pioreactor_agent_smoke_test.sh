#!/usr/bin/env bash

# Pioreactor Production Smoke Test
#
# Purpose: Run the quick, non-destructive checks on a Raspberry Pi Pioreactor. Continues on failure, reports errors in red.
#
# Usage (on the Pi):
#   chmod +x ./pioreactor_agent_smoke_test.sh
#   ./pioreactor_agent_smoke_test.sh
#
# Notes:
# - Run as the `pioreactor` user (not root).
# - Assumes official leader-worker image with `pio` CLI installed.
# - Requires `curl` and `jq`.

set -uo pipefail

FAILURE_COUNT=0
VERIFIED_IDLE_BEFORE=false
HAS_SYSTEMCTL=false

declare -a TEST_SEQUENCE=(
  check_versions
  check_configuration_files
  check_config_api_endpoints
  check_services
  check_mqtt_logging
  check_monitor_job
  check_database_access
  check_worker_model_metadata
  check_unit_api_core
  check_descriptor_endpoints
  check_unit_api_job_history
  check_installed_shared_assets
  check_blink
  check_pio_run_latency
  check_pio_logs_cli
  check_update_cli_contract
  check_repair_permissions_cli
  check_leader_api
  check_online_workers
  check_experiment_cli
  check_stirring_job
  check_experiment_scoping
  check_experiment_profiles
  check_exportable_datasets_listing
  check_export_datasets_endpoint
  check_dropin_plugin_discovery
  check_calibration_discovery
  check_broadcast_endpoints
  check_thermostat_job
  check_pump_actions
  check_plugin_install_cycle
  check_pios_cli
  check_pios_sync_configs
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

  if [[ -n "$jq_filter" ]]; then
    echo "$response" | jq -e "$jq_filter" >/dev/null
  else
    echo "$response" | jq . >/dev/null
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

curl_post_ok() {
  local url="$1"
  curl -fsS -X POST -d '' "$url" >/dev/null
}

poll_task_result_response() {
  # Usage: poll_task_result_response result_url_path [max_attempts]
  local result_url_path="$1"
  local max_attempts="${2:-120}"
  local response status

  for _ in $(seq 1 "$max_attempts"); do
    if ! response="$(curl -fsS "http://localhost${result_url_path}")"; then
      return 1
    fi

    status="$(echo "$response" | jq -r '.status // empty')"
    case "$status" in
      succeeded)
        printf '%s\n' "$response"
        return
        ;;
      failed)
        echo "$response" | jq -r '.error // .cause // "task failed"' >&2
        return 1
        ;;
      pending|running)
        sleep 1
        ;;
      *)
        echo "$response" | jq . >&2
        return 1
        ;;
    esac
  done

  return 1
}

poll_task_result() {
  # Usage: poll_task_result result_url_path jq_filter [max_attempts]
  local result_url_path="$1"
  local jq_filter="$2"
  local max_attempts="${3:-120}"
  local response

  if ! response="$(poll_task_result_response "$result_url_path" "$max_attempts")"; then
    return 1
  fi

  echo "$response" | jq -e "$jq_filter" >/dev/null
}

fetch_running_jobs() {
  curl -fsS http://localhost/unit_api/jobs/running
}

jobs_contain() {
  local jobs_json="$1"
  local jq_query="$2"

  echo "$jobs_json" | jq -e "$jq_query" >/dev/null
}

read_pwm_duty_cycle() {
  local raw
  if ! raw="$(pio cache view pwm_dc)"; then
    return 1
  fi

  if [[ "$raw" == \{* || "$raw" == \[* ]]; then
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
    "$config_dir/config_${hostname}.ini"
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
    "type==\"object\" and has(\"$hostname\") and (.[\"$hostname\"] | type==\"object\" and has(\"cluster.topology\"))"
  run_step \
    "Checking /api/config/units/\$broadcast" \
    curl_check \
    http://localhost/api/config/units/\$broadcast \
    'type=="object" and has("'"$hostname"'")'
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

ui_should_be_up() {
  if [[ "$HAS_SYSTEMCTL" != true ]]; then
    return 1
  fi

  systemctl is-active --quiet lighttpd
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
    fix_command="pio workers update-model ${hostname} -m pioreactor_40ml -v 1.5"
    fail "Worker model metadata missing for ${hostname}. Populate it with: ${fix_command}"
    return
  fi

  ok "Worker ${hostname} registered as ${model_name} v${model_version}"
}

check_unit_api_core() {
  run_step "Checking /unit_api/versions/app" curl_check http://localhost/unit_api/versions/app
  run_step "Checking /unit_api/jobs/running" curl_check http://localhost/unit_api/jobs/running 'type=="array"'
  run_step "Checking /unit_api/capabilities" curl_check http://localhost/unit_api/capabilities
  run_step "Checking /unit_api/system/utc_clock" curl_check http://localhost/unit_api/system/utc_clock
  run_step "Checking /unit_api/calibration_protocols" curl_check http://localhost/unit_api/calibration_protocols
  run_step "Checking /unit_api/calibrations" curl_check http://localhost/unit_api/calibrations
  run_step "Checking /unit_api/active_calibrations" curl_check http://localhost/unit_api/active_calibrations
}

check_descriptor_endpoints() {
  run_step \
    "Checking /unit_api/jobs/descriptors" \
    curl_check \
    http://localhost/unit_api/jobs/descriptors \
    'type=="array" and any(.job_name=="stirring") and any(.job_name=="self_test")'
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
  run_step \
    "Checking /unit_api/automations/descriptors/led" \
    curl_check \
    http://localhost/unit_api/automations/descriptors/led \
    'type=="array" and any(.automation_name=="light_dark_cycle") and any(.automation_name=="silent")'
  run_step \
    "Checking /api/automations/descriptors/led" \
    curl_check \
    http://localhost/api/automations/descriptors/led \
    'type=="array" and any(.automation_name=="light_dark_cycle")'
}

check_unit_api_job_history() {
  run_step "Checking /unit_api/jobs" curl_check http://localhost/unit_api/jobs 'type=="array"'
}

check_installed_shared_assets() {
  info "Checking installed shared Pioreactor assets"

  local expected_files=(
    "$HOME/.pioreactor/exportable_datasets/30_alt_media_fractions.yaml"
    "$HOME/.pioreactor/exportable_datasets/26_pwm_dcs.yaml"
    "$HOME/.pioreactor/exportable_datasets/27_raw_od_readings.yaml"
    "$HOME/.pioreactor/ui/jobs/50_self_test.yaml"
  )

  for file in "${expected_files[@]}"; do
    if [[ -f "$file" ]]; then
      ok "installed asset present: $file"
    else
      fail "missing installed asset: $file"
    fi
  done

  run_step \
    "Checking bundled exportable datasets are listed" \
    curl_check \
    http://localhost/api/datasets/exportable \
    'any(.dataset_name=="alt_media_fractions") and any(.dataset_name=="pwm_dcs") and any(.dataset_name=="raw_od_readings")'
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

check_update_cli_contract() {
  info "Checking update CLI command shape"

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
  info "Checking repair-permissions CLI"

  if pio repair-permissions --help | grep -q ".pioreactor"; then
    ok "pio repair-permissions help"
  else
    fail "pio repair-permissions help failed"
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
    if pio repair-permissions >/dev/null; then
      ok "pio repair-permissions completed"
    else
      fail "pio repair-permissions failed"
      rm -rf -- "$test_dir"
      return
    fi
  else
    fail "passwordless sudo is required for pio repair-permissions"
    rm -rf -- "$test_dir"
    return
  fi

  if [[ -g "$test_dir" ]] && \
     find "$test_dir" -maxdepth 0 -perm -020 -print -quit | grep -q . && \
     find "$test_file" -maxdepth 0 -perm -020 -print -quit | grep -q .; then
    ok "pio repair-permissions restored group-write and setgid bits"
  else
    fail "pio repair-permissions did not restore expected permissions on smoke test files"
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

  run_step "Checking /api/workers" curl_check http://localhost/api/workers
  run_step "Checking /api/units" curl_check http://localhost/api/units
  run_step "Checking /api/units/$hostname/capabilities" curl_check "http://localhost/api/units/$hostname/capabilities"
  run_step "Checking /api/units/$hostname/system/utc_clock" curl_check "http://localhost/api/units/$hostname/system/utc_clock"
  run_step "Checking /api/logs" curl_check http://localhost/api/logs
  run_step "Checking /api/local_access_point" curl_check http://localhost/api/local_access_point '.active | type=="boolean"'
}

fetch_worker_task_result() {
  # Usage: fetch_worker_task_result worker url [max_attempts]
  local worker="$1"
  local url="$2"
  local max_attempts="${3:-60}"
  local response result_url_path result_response

  if ! response="$(curl -fsS "$url")"; then
    return 1
  fi

  result_url_path="$(echo "$response" | jq -r '.result_url_path // empty')"
  if [[ -z "$result_url_path" ]]; then
    return 1
  fi

  if ! result_response="$(poll_task_result_response "$result_url_path" "$max_attempts")"; then
    return 1
  fi

  if ! echo "$result_response" | jq -e --arg worker "$worker" '.result | type=="object" and has($worker) and .[$worker] != null' >/dev/null; then
    return 1
  fi

  printf '%s\n' "$result_response"
}

check_worker_task_result() {
  # Usage: check_worker_task_result worker description url jq_filter [max_attempts]
  local worker="$1"
  local description="$2"
  local url="$3"
  local jq_filter="$4"
  local max_attempts="${5:-60}"
  local result_response

  info "$description"
  if result_response="$(fetch_worker_task_result "$worker" "$url" "$max_attempts")" && \
     echo "$result_response" | jq -e --arg worker "$worker" "$jq_filter" >/dev/null; then
    ok "$description"
  else
    fail "$description"
  fi
}

check_online_workers() {
  info "Checking online workers in the cluster"

  local hostname workers_json online_workers=() worker result_response
  hostname="$(hostname)"

  if ! workers_json="$(curl -fsS http://localhost/api/workers)"; then
    fail "Unable to fetch workers from leader API"
    return
  fi

  while IFS= read -r worker; do
    if [[ -z "$worker" || "$worker" == "$hostname" ]]; then
      continue
    fi

    if result_response="$(fetch_worker_task_result "$worker" "http://localhost/api/units/$worker/system/utc_clock" 30)" && \
       echo "$result_response" | jq -e --arg worker "$worker" '.result[$worker].clock_time | type=="string"' >/dev/null; then
      online_workers+=("$worker")
      ok "worker $worker is online"
    else
      warn "worker $worker is active in inventory but did not respond to utc_clock"
    fi
  done < <(echo "$workers_json" | jq -r '.[] | select(.is_active == 1 or .is_active == true) | .pioreactor_unit')

  if ((${#online_workers[@]} == 0)); then
    warn "No online non-leader workers found; skipping worker-specific checks"
    return
  fi

  for worker in "${online_workers[@]}"; do
    check_worker_task_result \
      "$worker" \
      "Checking worker $worker app version" \
      "http://localhost/api/units/$worker/versions/app" \
      '.result[$worker].version | type=="string" and length > 0'

    check_worker_task_result \
      "$worker" \
      "Checking worker $worker running jobs" \
      "http://localhost/api/units/$worker/jobs/running" \
      '.result[$worker] | type=="array"'

    run_step "Blinking worker $worker" curl_post_ok "http://localhost/api/workers/$worker/blink"
  done
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
experiment_profile_name: test_profile
YAML

  if http_json_ok http://localhost/api/experiment_profiles '.[] | select(.experimentProfile.experiment_profile_name == "test_profile")'; then
    ok "test_profile in experiment_profiles"
  else
    fail "test_profile not in experiment_profiles"
  fi

  rm -f ~/.pioreactor/experiment_profiles/test_profile.yaml
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

check_export_datasets_endpoint() {
  info "Testing export_datasets endpoint"
  local payload
  payload='{"datasets":["experiments","liquid_volumes"],"experiments":["<All experiments>"],"partition_by_unit":false,"partition_by_experiment":false}'
  local response

  if ! response="$(curl -fsS -X POST -H "Content-Type: application/json" -d "$payload" http://localhost/api/datasets/exportable/export)"; then
    fail "export_datasets request failed"
    return
  fi

  if echo "$response" | jq -e '.task_id and .result_url_path' >/dev/null; then
    local result_url_path filename
    result_url_path="$(echo "$response" | jq -r '.result_url_path')"

    if poll_task_result "$result_url_path" '.result.result == true and (.result.filename | endswith(".zip"))'; then
      filename="$(curl -fsS "http://localhost${result_url_path}" | jq -r '.result.filename // empty')"
      ok "export_datasets async task succeeded${filename:+ (file: $filename)}"

      if [[ -n "$filename" && -f "/run/pioreactor/exports/$filename" ]]; then
        ok "export file present: /run/pioreactor/exports/$filename"
      elif [[ -n "$filename" && -f "/var/www/pioreactorui/static/exports/$filename" ]]; then
        ok "export file present: /var/www/pioreactorui/static/exports/$filename"
      else
        warn "export file not found locally (may be transient or permissions)"
      fi
    else
      fail "export_datasets async task failed or timed out"
    fi
  elif echo "$response" | jq -e '.result == true' >/dev/null; then
    local filename
    filename="$(echo "$response" | jq -r '.filename // empty')"
    ok "export_datasets succeeded${filename:+ (file: $filename)}"
    if [[ -n "$filename" && -f "/var/www/pioreactorui/static/exports/$filename" ]]; then
      ok "export file present: /var/www/pioreactorui/static/exports/$filename"
    else
      warn "export file not found locally (may be transient or permissions)"
    fi
  else
    local msg
    msg="$(echo "$response" | jq -r '.msg // "unknown error"')"
    fail "export_datasets failed: $msg"
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

check_broadcast_endpoints() {
  info "Testing broadcast endpoints"
  local broadcast_literal='$broadcast'
  run_step "Checking /api/units/${broadcast_literal}/system/utc_clock" curl_check "http://localhost/api/units/\$broadcast/system/utc_clock"

  local jobs_map
  if jobs_map="$(curl -fsS "http://localhost/api/workers/\$broadcast/jobs/running")"; then
    if echo "$jobs_map" | jq -e 'type=="object"' >/dev/null; then
      ok "/api/workers/${broadcast_literal}/jobs/running returns mapping"
    else
      fail "/api/workers/${broadcast_literal}/jobs/running did not return a mapping"
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

check_plugin_install_cycle() {
  info "Testing plugin pioreactor-logs2slack install cycle"
  if pio plugins install pioreactor-logs2slack >/dev/null; then
    ok "installed pioreactor-logs2slack"
  else
    fail "plugin install failed"
  fi

  if pio plugins list | grep -q pioreactor-logs2slack; then
    ok "pioreactor-logs2slack listed"
  else
    fail "plugin not listed after install"
  fi

  if pio plugins uninstall pioreactor-logs2slack >/dev/null; then
    ok "uninstalled pioreactor-logs2slack"
  else
    fail "plugin uninstall failed"
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

check_pios_sync_configs() {
  info "Testing pios sync-configs"
  if pios sync-configs >/dev/null; then
    ok "pios sync-configs"
  else
    fail "pios sync-configs failed"
  fi
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
  require_cmd pio curl jq pios crudini sudo find

  info "Host: $(hostname)  IP: $(hostname -I || true)"

  run_tests

  cleanup
  summarize
}

main "$@"
