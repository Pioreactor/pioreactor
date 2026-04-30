# Tmpfiles Template

Systemd-tmpfiles rules for ephemeral Pioreactor runtime directories under `/run/pioreactor`.

The installer copies these rules into `/etc/tmpfiles.d` and runs `systemd-tmpfiles --create`.
