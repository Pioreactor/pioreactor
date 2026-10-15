# Installation parity between roles

Seed data lives in `packaging/shared-assets/`; maintained runtime files live in
`packaging/runtime-files/`. CustoPiZer and the generic Linux installer select
which services to install and enable from those shared sources.

`scripts/stage_common_assets.sh OUTPUT_DIRECTORY` builds a flat payload from
runtime service templates and SQL, config, hardware, camera, UI, export dataset
and experiment profile seeds. Both CustoPiZer and release updates use the same payload and
`packaging/runtime-files/bash/install_common_assets.sh` installer.

The installer adds missing descriptors, camera defaults and plugin directories on every unit.
It preserves existing files, including customized defaults, and stages config,
SQL, hardware and role-service templates under `/usr/share/pioreactor/provisioning`.
It does not create a database, change config, install live systemd units, reload
services, or enable a role. In particular, staging `avahi_aliases.service` outside
systemd prevents the existing common target from activating it on workers.

Fresh images seed their active hardware tree from the shared hardware sources.
Upgrades only stage those definitions: the hardware loader uses model-file presence
to enable modules, so filling gaps in an existing tree can undo a customization.
Runtime files are also not indiscriminately replaced by this additive installer;
changes to active scripts, services and configuration need explicit update steps.

For the preparation release, regenerate the sidecars with:

```sh
bash scripts/stage_common_assets.sh core/update_scripts/upcoming
```

The upgrade requires 26.11.0, which already supplies Mosquitto and the onboarding
helper on existing workers. No OS packages or network access are needed here.
The supported image baseline for this work is Trixie with Python 3.13.
Database initialization/migrations and config-driven role switching are separate
work. These staged seeds alone do not make leaving a cluster start a local leader.
