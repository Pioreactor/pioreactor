#!/usr/bin/env bash

set -euo pipefail

PIO_USER=pioreactor
PIO_HOME=/home/pioreactor
DOT_PIOREACTOR="$PIO_HOME/.pioreactor"
PIO_VENV=/opt/pioreactor/venv
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SHARED_ASSETS_DIR=$(cd -- "$SCRIPT_DIR/../shared-assets" && pwd)
INSTALLER_FILES_DIR="$SCRIPT_DIR/files"
UI_PORT=80
LEADER_HOSTNAME=$(hostname -s)
LEADER_ADDRESS=""
PACKAGE_SPEC=""
MQTT_PASSWORD=${MQTT_PASSWORD:-raspberry}

usage() {
  cat <<'EOF'
Usage:
  install.sh (--wheel PATH | --version VERSION | --git-ref REF) [options]

Options:
  --wheel PATH                Install a local Pioreactor wheel with the leader extra.
  --version VERSION           Install a Pioreactor GitHub release wheel.
  --git-ref REF               Install from the Pioreactor git repository ref.
  --leader-hostname HOSTNAME  Hostname recorded in Pioreactor config.
  --leader-address ADDRESS    Address workers use to reach this leader. Defaults to HOSTNAME.local.
  --ui-port PORT              Lighttpd/UI port. Defaults to 80.
  -h, --help                  Show this help.

Environment:
  MQTT_PASSWORD               Mosquitto password for the pioreactor MQTT user. Defaults to raspberry.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

quote_for_pip_extra() {
  local path=$1
  printf '%s[leader]' "$path"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --wheel)
      [ "$#" -ge 2 ] || die "--wheel requires a path"
      PACKAGE_SPEC=$(quote_for_pip_extra "$2")
      shift 2
      ;;
    --version)
      [ "$#" -ge 2 ] || die "--version requires a version"
      PACKAGE_SPEC="pioreactor[leader] @ https://github.com/Pioreactor/pioreactor/releases/download/$2/pioreactor-$2-py3-none-any.whl"
      shift 2
      ;;
    --git-ref)
      [ "$#" -ge 2 ] || die "--git-ref requires a ref"
      PACKAGE_SPEC="pioreactor[leader] @ git+https://github.com/Pioreactor/pioreactor.git@$2#subdirectory=core"
      shift 2
      ;;
    --leader-hostname)
      [ "$#" -ge 2 ] || die "--leader-hostname requires a value"
      LEADER_HOSTNAME=$2
      shift 2
      ;;
    --leader-address)
      [ "$#" -ge 2 ] || die "--leader-address requires a value"
      LEADER_ADDRESS=$2
      shift 2
      ;;
    --ui-port)
      [ "$#" -ge 2 ] || die "--ui-port requires a value"
      UI_PORT=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

[ -n "$PACKAGE_SPEC" ] || die "Provide one of --wheel, --version, or --git-ref"
[ "$(id -u)" -eq 0 ] || die "Run as root"
case "$UI_PORT" in
  ''|*[!0-9]*) die "--ui-port must be an integer" ;;
esac

if [ -z "$LEADER_ADDRESS" ]; then
  LEADER_ADDRESS="$LEADER_HOSTNAME.local"
fi

require_debian_13() {
  # shellcheck source=/dev/null
  . /etc/os-release
  [ "${ID:-}" = "debian" ] || die "Only Debian 13 is supported by this installer right now"
  [ "${VERSION_ID:-}" = "13" ] || die "Only Debian 13 is supported by this installer right now"
  command -v systemctl >/dev/null 2>&1 || die "systemd is required"
}

install_apt_dependencies() {
  apt-get update
  apt-get install -y \
    acl \
    avahi-daemon \
    avahi-utils \
    git \
    jq \
    lighttpd \
    logrotate \
    mosquitto \
    mosquitto-clients \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    rsyslog \
    rsync \
    sqlite3 \
    ufw
}

ensure_pioreactor_user() {
  if ! id "$PIO_USER" >/dev/null 2>&1; then
    adduser --system --home "$PIO_HOME" --shell /bin/bash --group "$PIO_USER"
  fi

  for group_name in www-data systemd-journal; do
    if getent group "$group_name" >/dev/null; then
      usermod -a -G "$group_name" "$PIO_USER"
    fi
  done

  chmod 755 "$PIO_HOME"
}

install_python_package() {
  install -d -o "$PIO_USER" -g "$PIO_USER" /opt/pioreactor
  if [ ! -x "$PIO_VENV/bin/python" ]; then
    runuser -u "$PIO_USER" -- python3 -m venv "$PIO_VENV"
  fi
  runuser -u "$PIO_USER" -- "$PIO_VENV/bin/pip" install --upgrade pip
  runuser -u "$PIO_USER" -- "$PIO_VENV/bin/pip" install crudini
  runuser -u "$PIO_USER" -- "$PIO_VENV/bin/pip" install \
    --index-url https://pypi.org/simple \
    --extra-index-url https://www.piwheels.org/simple \
    "$PACKAGE_SPEC"
}

install_environment_and_wrappers() {
  install -D -o root -g root -m 0644 "$INSTALLER_FILES_DIR/pioreactor.env" /etc/pioreactor.env

  for executable_name in pio pios; do
    cat >"/usr/local/bin/$executable_name" <<EOF
#!/bin/sh
set -a
. /etc/pioreactor.env
set +a
exec /opt/pioreactor/venv/bin/$executable_name "\$@"
EOF
    chmod 0755 "/usr/local/bin/$executable_name"
  done
}

install_static_asset_link() {
  local static_dir
  static_dir=$("$PIO_VENV/bin/python" -c 'from pathlib import Path; import pioreactor.web; print(Path(pioreactor.web.__file__).parent / "static")')
  install -d -o root -g root -m 0755 /usr/share/pioreactorui
  ln -sfn "$static_dir" /usr/share/pioreactorui/static
}

install_system_files() {
  install -d -o root -g root -m 0755 /etc/systemd/system
  install -m 0644 "$INSTALLER_FILES_DIR"/systemd/* /etc/systemd/system/

  install -d -o root -g root -m 0755 /etc/lighttpd
  install -d -o root -g root -m 0755 /etc/lighttpd/conf-available
  install -m 0644 "$INSTALLER_FILES_DIR/lighttpd/lighttpd.conf" /etc/lighttpd/lighttpd.conf
  sed -i "s/server.port                 = 80/server.port                 = $UI_PORT/" /etc/lighttpd/lighttpd.conf
  install -m 0644 "$INSTALLER_FILES_DIR/lighttpd"/10-expire.conf /etc/lighttpd/conf-available/
  install -m 0644 "$INSTALLER_FILES_DIR/lighttpd"/50-pioreactorui.conf /etc/lighttpd/conf-available/
  install -m 0644 "$INSTALLER_FILES_DIR/lighttpd"/51-cors.conf /etc/lighttpd/conf-available/

  lighttpd-enable-mod expire
  lighttpd-enable-mod fastcgi
  lighttpd-enable-mod rewrite
  lighttpd-enable-mod pioreactorui
  lighttpd-enable-mod cors

  install -D -o root -g root -m 0644 "$INSTALLER_FILES_DIR/tmpfiles.d/pioreactor.conf" /etc/tmpfiles.d/pioreactor.conf
  install -D -o root -g root -m 0644 "$INSTALLER_FILES_DIR/logrotate/pioreactor" /etc/logrotate.d/pioreactor
  systemd-tmpfiles --create /etc/tmpfiles.d/pioreactor.conf
}

configure_mosquitto() {
  install -d -o mosquitto -g mosquitto -m 0750 /etc/mosquitto
  printf 'pioreactor:%s\n' "$MQTT_PASSWORD" >/etc/mosquitto/pw.txt
  mosquitto_passwd -U /etc/mosquitto/pw.txt
  chown mosquitto:mosquitto /etc/mosquitto/pw.txt
  chmod 0700 /etc/mosquitto/pw.txt

  install -d -o root -g root -m 0755 /etc/mosquitto/conf.d
  cat >/etc/mosquitto/conf.d/pioreactor.conf <<'EOF'
log_type error
log_type warning
persistence false
listener 1883
protocol mqtt
listener 9001
protocol websockets
allow_anonymous false
max_inflight_messages 1000
password_file /etc/mosquitto/pw.txt
EOF
}

create_dot_pioreactor_tree() {
  install -d -o "$PIO_USER" -g www-data -m 2775 "$DOT_PIOREACTOR"
  install -d -o "$PIO_USER" -g www-data -m 2775 "$DOT_PIOREACTOR/storage"
  install -d -o "$PIO_USER" -g www-data -m 2775 "$DOT_PIOREACTOR/plugins"
  install -d -o "$PIO_USER" -g www-data -m 2775 "$DOT_PIOREACTOR/plugins/ui/jobs"
  install -d -o "$PIO_USER" -g www-data -m 2775 "$DOT_PIOREACTOR/plugins/ui/automations/dosing"
  install -d -o "$PIO_USER" -g www-data -m 2775 "$DOT_PIOREACTOR/plugins/ui/automations/led"
  install -d -o "$PIO_USER" -g www-data -m 2775 "$DOT_PIOREACTOR/plugins/ui/automations/temperature"
  install -d -o "$PIO_USER" -g www-data -m 2775 "$DOT_PIOREACTOR/plugins/ui/charts"
  install -d -o "$PIO_USER" -g www-data -m 2775 "$DOT_PIOREACTOR/plugins/exportable_datasets"
  install -d -o "$PIO_USER" -g www-data -m 2775 "$DOT_PIOREACTOR/experiment_profiles"
  install -d -o "$PIO_USER" -g www-data -m 2775 "$DOT_PIOREACTOR/exportable_datasets"
  install -d -o "$PIO_USER" -g www-data -m 2775 "$DOT_PIOREACTOR/ui"

  if [ ! -f "$DOT_PIOREACTOR/config.ini" ]; then
    install -o "$PIO_USER" -g www-data -m 0664 "$SHARED_ASSETS_DIR/pioreactor/config.example.ini" "$DOT_PIOREACTOR/config.ini"
  fi
  if [ ! -f "$DOT_PIOREACTOR/unit_config.ini" ]; then
    install -o "$PIO_USER" -g www-data -m 0664 /dev/null "$DOT_PIOREACTOR/unit_config.ini"
  fi

  rsync -a --chown="$PIO_USER":www-data "$SHARED_ASSETS_DIR/pioreactor/exportable_datasets/" "$DOT_PIOREACTOR/exportable_datasets/"
  rsync -a --chown="$PIO_USER":www-data "$SHARED_ASSETS_DIR/pioreactor/ui/" "$DOT_PIOREACTOR/ui/"
}

initialize_databases_and_config() {
  local db_path="$DOT_PIOREACTOR/storage/pioreactor.sqlite"
  local metadata_db_path="$DOT_PIOREACTOR/storage/local_persistent_pioreactor_metadata.sqlite"

  sqlite3 "$db_path" < "$SHARED_ASSETS_DIR/sql/sqlite_configuration.sql"
  sqlite3 "$db_path" < "$SHARED_ASSETS_DIR/sql/create_tables.sql"
  sqlite3 "$db_path" < "$SHARED_ASSETS_DIR/sql/create_triggers.sql"
  sqlite3 "$metadata_db_path" < "$SHARED_ASSETS_DIR/sql/sqlite_configuration.sql"

  runuser -u "$PIO_USER" -- "$PIO_VENV/bin/crudini" --ini-options=nospace --set "$DOT_PIOREACTOR/config.ini" cluster.topology leader_hostname "$LEADER_HOSTNAME"
  runuser -u "$PIO_USER" -- "$PIO_VENV/bin/crudini" --ini-options=nospace --set "$DOT_PIOREACTOR/config.ini" cluster.topology leader_address "$LEADER_ADDRESS"
  runuser -u "$PIO_USER" -- "$PIO_VENV/bin/crudini" --ini-options=nospace --set "$DOT_PIOREACTOR/config.ini" mqtt broker_address "$LEADER_ADDRESS"
  runuser -u "$PIO_USER" -- "$PIO_VENV/bin/crudini" --ini-options=nospace --set "$DOT_PIOREACTOR/config.ini" ui port "$UI_PORT"

  runuser -u "$PIO_USER" -- "$PIO_VENV/bin/crudini" --ini-options=nospace --set "$DOT_PIOREACTOR/unit_config.ini" cluster.topology leader_address 127.0.0.1
  runuser -u "$PIO_USER" -- "$PIO_VENV/bin/crudini" --ini-options=nospace --set "$DOT_PIOREACTOR/unit_config.ini" mqtt broker_address 127.0.0.1

  sqlite3 "$db_path" "INSERT OR IGNORE INTO experiments (created_at, experiment, description) VALUES (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'), 'Demo experiment', 'This is a demo experiment. Feel free to click around. When you are ready, create a new experiment in the dropdown to the left.');"

  chown -R "$PIO_USER":www-data "$DOT_PIOREACTOR"
  chmod -R g+rw "$DOT_PIOREACTOR"
  find "$DOT_PIOREACTOR" -type d -exec chmod g+s {} +
}

enable_and_start_services() {
  systemctl daemon-reload
  systemctl enable pioreactor.target
  systemctl enable pioreactor-leader.target
  systemctl enable pioreactor-web.target
  systemctl restart mosquitto.service
  systemctl restart pioreactor-web.target
  systemctl restart pioreactor-leader.target
}

main() {
  require_debian_13
  install_apt_dependencies
  ensure_pioreactor_user
  install_python_package
  install_environment_and_wrappers
  install_static_asset_link
  install_system_files
  configure_mosquitto
  create_dot_pioreactor_tree
  initialize_databases_and_config
  enable_and_start_services

  echo "Pioreactor leader installed."
  echo "UI: http://$LEADER_ADDRESS:$UI_PORT"
  echo "Set workers to use leader_address=$LEADER_ADDRESS and mqtt broker_address=$LEADER_ADDRESS."
}

main "$@"
