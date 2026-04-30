# Shared Provisioning Assets

This directory is the source of truth for one-time Pioreactor provisioning data that is shared between install paths.

Consumers:

- `packaging/linux-leader/install.sh`, when initializing a Debian 13 leader-only workstation.
- `../CustoPiZer/scripts/sync_pioreactor_assets.sh`, before building Raspberry Pi images.

These files are not included in the Python wheel. They are copied into target runtime locations such as `/home/pioreactor/.pioreactor` or CustoPiZer `workspace/scripts/files`.

## Contents

- `sql/`: SQLite initialization scripts.
- `pioreactor/config.example.ini`: default shared Pioreactor configuration.
- `pioreactor/exportable_datasets/`: built-in dataset export definitions copied into `~/.pioreactor/exportable_datasets`.
- `pioreactor/ui/`: built-in job, automation, and chart descriptors copied into `~/.pioreactor/ui`.
