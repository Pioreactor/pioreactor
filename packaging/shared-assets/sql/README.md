# SQL Seed Assets

SQLite scripts used to initialize Pioreactor storage during provisioning.

- `sqlite_configuration.sql`: database pragmas/configuration applied to Pioreactor SQLite files.
- `create_tables.sql`: base application schema for the leader database.
- `create_triggers.sql`: triggers associated with the base schema.

These are install/image seed files, not runtime Python package data. Update scripts remain under `core/update_scripts/`.
