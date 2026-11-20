# Update scripts

Possible update scripts and their sequence, always run as `root`:
- `pre_update.sh` runs (if exists)
- Following this, `pip install pioreactor...whl` runs
- `update.sh` runs (if exists)
- `update.sql` to update sqlite schema runs (if exists), on every unit that has the `storage.database` file, not only the leader
- `post_update.sh` runs (if exists). Useful for restarting jobs, adding data to new db tables, or rebooting RPis.


It's very important that update scripts are idempotent. Some tips:

 - Use ChatGPT to inspect if a script is idempotent, or make suggestions.


### `bash` specific tips
 - the scripts are run as `root` user, so `pios sync-configs` fails with auth problems. Use `sudo -u pioreactor pios sync-configs`
 - use `|| :` if a command may fail, but you want to continue anyways
 - use `trap` and `EXIT` semantics (like try / expect) to force some code block to always run.
 - https://arslan.io/2019/07/03/how-to-write-idempotent-bash-scripts/


### Checking for leader in script:

Pick the check by what the step does:

 - **Provisioning** (installing files such as chart YAMLs, packages, database schema or data migrations): check that the unit *can* be a leader, so a leader-worker that joined another cluster stays current for when it leaves. `pioreactor-leader.target` stays enabled after joining.

```
if systemctl is-enabled --quiet pioreactor-leader.target; then
  ...
fi
```

   For database work, check that the database file exists instead (`update.sql` already does).

 - **Acting on the running role** (for example restarting `mqtt_to_db_streaming`): check that the unit *is* the leader now:

```
# Get the hostname
HOSTNAME=$(hostname)

# Get the leader hostname
# Don't use `leader_address`, as users do change that.
LEADER_HOSTNAME=$(crudini --get $PIO_DIR/config.ini cluster.topology leader_hostname)

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then
  ...
fi

```


### SQL specific tips
 - `update.sql` also runs on non-leaders that have the database (e.g. a leader-worker that joined another cluster). Don't assume the unit is the leader. Gate other database migrations in scripts on the database file existing, not on the leader check above.
 - use `IF EXISTS`
 - `$experiment` (`UNIVERSAL_EXPERIMENT`) intentionally represents activity outside a named experiment and has no required parent row in `experiments`. Telemetry and activity-rollup rows for it can appear in `PRAGMA foreign_key_check`; do not require an empty result or delete these records as corrupt. Compare pre/post-migration relationships or explicitly account for this placeholder, while rejecting newly introduced violations. Other missing experiment names are not automatically valid.
