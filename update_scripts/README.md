# Update scripts

Possible update scripts and their sequence:
- `pre_update.sh` runs (if exists)
- Following this, `pip install pioreactor...whl` runs
- `update.sh` runs (if exists)
- `update.sql` to update sqlite schema runs (if exists)
- `post_update.sh` runs (if exists). Useful for restarting jobs, or rebooting RPis.



It's very important that update scripts are idempotent. Some tips:

 - Use ChatGPT to assist psuedo-check if a script is idempotent, or making suggestions.

### bash specific tips
 - https://arslan.io/2019/07/03/how-to-write-idempotent-bash-scripts/
 - use `|| true` if a command may fail, but you want to continue


### SQL specific tips
 - use `IF EXISTS`
