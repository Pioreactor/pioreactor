#!/usr/bin/env bash
set -euo pipefail
exec 2>/dev/null

# Helper to check whether common dev services are already running.

running_services=()
missing_services=()

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

check_port() {
	local name=$1
	local port=$2
	local details
	# Skip header (NR>1) and capture the first listener to keep output compact.
	details=$(lsof -nPiTCP:${port} -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {printf "%s (pid %s)", $1, $2; exit}')
	if [[ -n "${details}" ]]; then
		add_running "${name}" "port ${port} – ${details}"
	else
		add_missing "${name}" "port ${port} free"
	fi
}

check_huey() {
	local pattern="huey_consumer.*pioreactor\\.web\\.tasks\\.huey"
	local details summary count
	details=$(pgrep -fl "${pattern}" || true)
	if [[ -n "${details}" ]]; then
		summary=$(printf '%s\n' "${details}" | head -n1)
		count=$(printf '%s\n' "${details}" | awk 'END {print NR}')
		if [[ ${count} -gt 1 ]]; then
			summary+=" (+$((count - 1)) more)"
		fi
		add_running "Huey consumer" "${summary}"
	else
		add_missing "Huey consumer" "run 'make huey-dev'"
	fi
}

check_port "Flask web API" 4999
check_port "Frontend dev server" 3000
check_huey

print_summary() {
	if [[ ${#missing_services[@]} -eq 0 ]]; then
		local joined_running
		joined_running=$(IFS='; '; echo "${running_services[*]}")
		echo "All dev services appear to be running: ${joined_running}"
	else
		echo "Need to start:"
		for svc in "${missing_services[@]}"; do
			echo " - ${svc}"
		done
		if [[ ${#running_services[@]} -gt 0 ]]; then
			local joined_running
			joined_running=$(IFS='; '; echo "${running_services[*]}")
			echo "Already running: ${joined_running}"
		fi
	fi
}

print_summary
