# Update scripts

Possible update scripts and their sequence:
- `pre_update.sh` runs (if exists)
- Following this, `pip install pioreactor...whl` runs
- `update.sh` runs (if exists)
- `update.sql` to update sqlite schema runs (if exists)
- `post_update.sh` runs (if exists). Useful for restarting jobs, or rebooting RPis.



It's very important that update scripts are idempotent. Some tips:

 - Use ChatGPT to assist psuedo-check if a script is idempotent, or making suggestions.
 - If needed, version the github urls to a commit. Example:
    ```
    https://raw.githubusercontent.com/Pioreactor/CustoPiZer/e27ec/workspace/scripts/files/bash/install_pioreactor_plugin.sh
    ```
    where `e27ec` is the commit (or a branch name).

### bash specific tips
 - use `|| true` if a command may fail, but you want to continue anyways
 - use `trap` and `EXIT` semantics (like try / expect) to force some code block to always run.
 - https://arslan.io/2019/07/03/how-to-write-idempotent-bash-scripts/


### SQL specific tips
 - use `IF EXISTS`
