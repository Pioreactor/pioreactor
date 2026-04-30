# Pioreactor Dotdir Seed Assets

Files copied into the Pioreactor data root, normally `/home/pioreactor/.pioreactor`, during image build or Linux leader installation.

- `config.example.ini` seeds `~/.pioreactor/config.ini` if no config exists.
- `exportable_datasets/` seeds built-in export definitions.
- `ui/` seeds built-in UI descriptors for jobs, automations, and charts.

Installers should preserve existing user data and only initialize missing config/database state.
