# Exportable Dataset Descriptors

Built-in dataset export definitions copied to `~/.pioreactor/exportable_datasets`.

`$experiment` is the intentional virtual experiment for activity such as self-tests and system logs. It need not exist in the `experiments` table. Queries joining experiment metadata should preserve these rows with a left join; `hours_since_experiment_started` is NULL (an empty CSV field) when no experiment start exists. Do not treat those rows as corrupt or invent a start time for them.

Each YAML file describes one dataset exposed by the Pioreactor export flow. These files are copied during provisioning so deployments can later add, remove, or override dataset descriptors in the Pioreactor data root without changing the Python package.
