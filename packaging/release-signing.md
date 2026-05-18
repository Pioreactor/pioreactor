# Release Archive Signing

Pioreactor release archives are executable update payloads. A `release_<version>.zip`
contains scripts such as `pre_update.sh`, `update.sh`, and `post_update.sh` that
are run by `pio update app` during software updates. Those scripts may run as
root, so an uploaded release archive must be treated as software, not as an
ordinary data file.

The release archive format uses a signed manifest inside the zip:

```text
release_26.4.2.zip
  pioreactor-release-manifest.json
  pioreactor-release-manifest.json.sig
  CHANGELOG.md
  pre_update.sh
  update.sh
  post_update.sh
  update.sql
  wheels_26.4.2.zip
  pioreactor-26.4.2-py3-none-any.whl
  optional-sidecar-files
```

The manifest lists every file in the archive, including sidecar files, and
records each file's SHA-256 hash. The signature proves that the manifest was
created by whoever controls the Pioreactor release-signing private key. During
an update, Pioreactor verifies the signature and checks every file hash before
any update script is extracted or executed.

## Why this exists

Pioreactors are often updated from uploaded archives because not every device
has internet access. User uploads must remain supported, but a raw uploaded zip
must not become trusted root script execution just because it is named like a
release.

Signing gives us offline authenticity:

- the device ships with a trusted public key
- the release workflow signs each release manifest with the private key
- verification needs no internet access
- a modified archive fails hash verification
- a forged archive fails signature verification

This does not make update scripts harmless. It makes the release-signing key the
trust boundary for update scripts.

## Generate the signing key

Generate an OpenSSH Ed25519 key pair on an admin machine:

```bash
mkdir -p ~/.pioreactor-release-signing
chmod 700 ~/.pioreactor-release-signing

ssh-keygen \
  -t ed25519 \
  -f ~/.pioreactor-release-signing/pioreactor_release_signing_key \
  -C "pioreactor-release-$(date +%Y-%m-%d)" \
  -N ""
```

This creates:

```text
~/.pioreactor-release-signing/pioreactor_release_signing_key
~/.pioreactor-release-signing/pioreactor_release_signing_key.pub
```

The private key must not be committed. The public key is safe to commit.

## Configure the verifier

Copy the full public key line:

```bash
cat ~/.pioreactor-release-signing/pioreactor_release_signing_key.pub
```

It should look like:

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... pioreactor-release-2026-05-17
```

Paste that full line into `core/pioreactor/release_archive.py`:

```python
TRUSTED_RELEASE_SIGNING_PUBLIC_KEY = "ssh-ed25519 AAAAC3... pioreactor-release-2026-05-17"
```

Forks should generate their own key pair and commit their own public key. Do not
reuse Pioreactor's private signing key for a fork.

## Configure GitHub Actions

Add the private key as a repository secret named:

```text
PIOREACTOR_RELEASE_SIGNING_KEY
```

Using the GitHub CLI:

```bash
gh secret set PIOREACTOR_RELEASE_SIGNING_KEY \
  --repo Pioreactor/pioreactor \
  < ~/.pioreactor-release-signing/pioreactor_release_signing_key
```

Using the GitHub UI, paste the entire private key, including:

```text
-----BEGIN OPENSSH PRIVATE KEY-----
...
-----END OPENSSH PRIVATE KEY-----
```

The release workflow refuses to publish `release_<version>.zip` if this secret
is missing.

## Sanity-check the key pair

Before relying on the key in a release, verify a test payload locally:

```bash
printf '{"test":"pioreactor-release"}\n' > /tmp/pioreactor-release-manifest.json

ssh-keygen -Y sign \
  -f ~/.pioreactor-release-signing/pioreactor_release_signing_key \
  -n pioreactor-release \
  /tmp/pioreactor-release-manifest.json

printf 'pioreactor-release %s\n' \
  "$(cat ~/.pioreactor-release-signing/pioreactor_release_signing_key.pub)" \
  > /tmp/pioreactor-allowed-signers

ssh-keygen -Y verify \
  -f /tmp/pioreactor-allowed-signers \
  -I pioreactor-release \
  -n pioreactor-release \
  -s /tmp/pioreactor-release-manifest.json.sig \
  < /tmp/pioreactor-release-manifest.json
```

Expected success output includes:

```text
Good "pioreactor-release" signature
```

## Release archive contents

The required files are:

```text
CHANGELOG.md
pre_update.sh
update.sh
post_update.sh
update.sql
wheels_<version>.zip
pioreactor-<version>-py3-none-any.whl
```

Additional sidecar files are allowed. Sidecars must be flat files in the release
archive root, must be listed in `pioreactor-release-manifest.json`, and must
match their manifest hashes. This matches the update-script convention that
sidecar assets live beside `update.sh`.

## Operational notes

- Keep the private key in GitHub Actions secrets or another restricted secret
  store.
- Do not add a passphrase to the CI signing key unless the workflow is also
  updated to provide it non-interactively.
- Rotate the key by generating a new key pair, committing the new public key,
  and replacing the GitHub secret. Existing releases signed by the old key will
  no longer verify after the public key changes.
- `ssh-keygen -Y verify` is required on devices that verify release archives.
  Pioreactor installs `openssh-client`; forks should make the same runtime
  requirement explicit.
- The first release that introduces verification can still be installed by old
  versions that do not verify manifests. After that, future archive updates
  require signed manifests.

## Files involved

- `.github/workflows/build.yaml`: creates the manifest, signs it, and includes
  both manifest files in `release_<version>.zip`.
- `core/pioreactor/release_archive.py`: verifies signed release archives.
- `core/pioreactor/cli/pio.py`: runs verification before extracting release
  archives or executing update scripts.
- `core/pioreactor/web/api.py`: verifies uploaded archives before queueing
  update tasks.
