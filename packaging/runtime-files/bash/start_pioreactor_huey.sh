#!/bin/sh

set -eu

huey_consumer="${PIO_VENV:-/opt/pioreactor/venv}/bin/huey_consumer"
image_profile="${PIOREACTOR_IMAGE_PROFILE:-standard}"

case "$image_profile" in
  zero_w_worker)
    exec "$huey_consumer" pioreactor.web.tasks.huey -b 1.0 -w 1 -f -C -d 0.25
    ;;
  *)
    exec "$huey_consumer" pioreactor.web.tasks.huey -b 1.0 -w 10 -f -C -d 0.01
    ;;
esac
