# Update scripts

Possible update scripts and their sequence, always run as `root`:
- `pre_update.sh` runs (if exists)
- Following this, `pip install pioreactor...whl` runs
- `update.sh` runs (if exists)
- `update.sql` to update sqlite schema runs (if exists)
- `post_update.sh` runs (if exists). Useful for restarting jobs, adding data to new db tables, or rebooting RPis.


It's very important that update scripts are idempotent. Some tips:

 - Use ChatGPT to assist psuedo-check if a script is idempotent, or making suggestions.


### bash specific tips
 - the scripts are run as `root` user, so `pios sync-configs` fails with auth problems. Use `sudo -u pioreactor pios sync-configs`
 - use `|| :` if a command may fail, but you want to continue anyways
 - use `trap` and `EXIT` semantics (like try / expect) to force some code block to always run.
 - https://arslan.io/2019/07/03/how-to-write-idempotent-bash-scripts/


### SQL specific tips
 - use `IF EXISTS`
