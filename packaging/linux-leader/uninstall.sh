#!/usr/bin/env bash

set -euo pipefail

[ "$(id -u)" -eq 0 ] || {
  echo "error: Run as root" >&2
  exit 1
}

systemctl disable --now pioreactor-leader.target >/dev/null 2>&1 || true
systemctl disable --now pioreactor-web.target >/dev/null 2>&1 || true
systemctl disable --now pioreactor.target >/dev/null 2>&1 || true
systemctl daemon-reload

cat <<'EOF'
Pioreactor leader services were disabled.

Preserved data:
  /home/pioreactor/.pioreactor
  /opt/pioreactor/venv
  /etc/pioreactor.env

Remove those manually only after exporting or backing up experiment data.
EOF
