# Linux Leader Service Templates

Templates installed by `packaging/linux-leader/install.sh` onto a Debian 13 leader-only workstation.

These files describe host-level runtime services and should remain separate from `packaging/shared-assets`, which contains application seed data copied into `.pioreactor`.

## Contents

- `systemd/`: leader-only service and target units.
- `lighttpd/`: web server and FastCGI configuration.
- `tmpfiles.d/`: `/run/pioreactor` runtime directory rules.
- `logrotate/`: Pioreactor log rotation config.
- `pioreactor.env`: shared environment loaded by services and CLI wrappers.
