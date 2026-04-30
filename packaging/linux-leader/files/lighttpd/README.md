# Lighttpd Templates

Lighttpd configuration for a Debian 13 leader-only workstation.

The installer copies these into `/etc/lighttpd` and `/etc/lighttpd/conf-available`, then enables the required modules. The leader serves the React static bundle and proxies API paths into `pioreactor-fcgi`.

Worker-only API restrictions live in CustoPiZer, not here.
