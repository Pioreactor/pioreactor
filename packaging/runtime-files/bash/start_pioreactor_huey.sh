#!/bin/sh

set -eu

huey_consumer="${PIO_VENV:-/opt/pioreactor/venv}/bin/huey_consumer"
online_cpu_count="$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf '0\n')"

case "$online_cpu_count" in
  1)
    exec "$huey_consumer" pioreactor.web.tasks.huey -b 1.0 -w 2 -f -C -d 0.25
    ;;
  *)
    exec "$huey_consumer" pioreactor.web.tasks.huey -b 1.0 -w 10 -f -C -d 0.01
    ;;
esac
