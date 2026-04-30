# Systemd Templates

Systemd units for a Debian 13 leader-only workstation.

These units start the web stack, Huey, leader background jobs, database backup timer, and export cleanup timer. They intentionally exclude Raspberry Pi image-only services such as firstboot, RP2040 loading, local access point setup, and worker targets.

CustoPiZer owns the image-specific systemd graph.
