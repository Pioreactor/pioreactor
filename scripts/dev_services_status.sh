#!/usr/bin/env bash
set -euo pipefail
exec 2>/dev/null

# Helper to check whether common dev services are already running.

running_services=()
missing_services=()
unknown_services=()

add_running() {
	local name=$1
	local detail=$2
	running_services+=("${name} (${detail})")
}

add_missing() {
	local name=$1
	local hint=$2
	missing_services+=("${name} (${hint})")
}

add_unknown() {
	local name=$1
	local detail=$2
	unknown_services+=("${name} (${detail})")
}

check_port() {
	local name=$1
	local port=$2
	local details
	# Skip header (NR>1) and capture the first listener to keep output compact.
	details=$(lsof -nPiTCP:${port} -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {printf "%s (pid %s)", $1, $2; exit}' || true)
	if [[ -n "${details}" ]]; then
		add_running "${name}" "port ${port} – ${details}"
	else
		add_missing "${name}" "port ${port} free"
	fi
}

check_huey() {
	local pattern="huey_consumer.*pioreactor\\.web\\.tasks\\.huey"
	local details summary count pgrep_status
	if details=$(pgrep -fl "${pattern}"); then
		summary=$(printf '%s\n' "${details}" | head -n1)
		count=$(printf '%s\n' "${details}" | awk 'END {print NR}')
		if [[ ${count} -gt 1 ]]; then
			summary+=" (+$((count - 1)) more)"
		fi
		add_running "Huey consumer" "${summary}"
	else
		pgrep_status=$?
		if [[ ${pgrep_status} -eq 1 ]]; then
			add_missing "Huey consumer" "run 'make huey-dev'"
		else
			add_unknown "Huey consumer" "unable to inspect process list"
		fi
	fi
}

check_port "Flask web API" 4999
check_port "Frontend dev server" 3000
check_huey

print_summary() {
	if [[ ${#missing_services[@]} -eq 0 && ${#unknown_services[@]} -eq 0 ]]; then
		local joined_running
		joined_running=$(IFS='; '; echo "${running_services[*]}")
		echo "All dev services appear to be running: ${joined_running}"
	else
		if [[ ${#missing_services[@]} -gt 0 ]]; then
			echo "Need to start:"
			for svc in "${missing_services[@]}"; do
				echo " - ${svc}"
			done
		fi
		if [[ ${#unknown_services[@]} -gt 0 ]]; then
			echo "Unable to verify:"
			for svc in "${unknown_services[@]}"; do
				echo " - ${svc}"
			done
		fi
		if [[ ${#running_services[@]} -gt 0 ]]; then
			local joined_running
			joined_running=$(IFS='; '; echo "${running_services[*]}")
			echo "Already running: ${joined_running}"
		fi
	fi
}

print_summary
