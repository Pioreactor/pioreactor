# Getting Started

This guide gets the Pioreactor monorepo running on a development laptop:

- Flask web API: `make web-dev`
- React frontend: `make frontend-dev`
- Huey task consumer: `make huey-dev`
- Local CLI: `pio`

The development flow is POSIX-shell based. On macOS, use Terminal. On Windows, use WSL2 with Ubuntu rather than PowerShell or native `cmd.exe`.

## 1. Install system dependencies

### macOS

Install Homebrew if needed, then install the basic runtime tools:

```bash
brew install python@3.13 node@20 direnv make mosquitto
```


Make sure `python3.13`, `node`, `npm`, `make`, and `direnv` are available:

```bash
python3.13 --version
node --version
npm --version
make --version
direnv --version
```

### Windows

Use WSL2:

```powershell
wsl --install -d Ubuntu
```

Open Ubuntu, then install the base tools:

```bash
sudo apt update
sudo apt install -y build-essential curl git make direnv mosquitto
```

Install Python 3.13 and Node 20. The most reliable cross-distro option is `pyenv` for Python and `nvm` for Node:

```bash
curl https://pyenv.run | bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
```

Restart the Ubuntu shell, then:

```bash
pyenv install 3.13.0
pyenv global 3.13.0
nvm install 20
nvm use 20
```

Confirm:

```bash
python3.13 --version
node --version
npm --version
```

Keep the repo inside the Linux filesystem, for example `~/code/pioreactor`, not under `/mnt/c/...`. File watching and virtualenv behavior are much better there.

## 2. Clone the repo

```bash
git clone https://github.com/Pioreactor/pioreactor.git
cd pioreactor
```

If you already have the repo, start from its root directory.

## 3. Create local development state

The app expects a Pioreactor data root with config, storage, plugins, and export directories. For local development, keep that under the repo as `.pioreactor`.

```bash
mkdir -p .pioreactor/storage .pioreactor/cache .pioreactor/plugins .pioreactor/experiment_profiles .pioreactor/exportable_datasets plugins_dev
cp -n config.dev.ini .pioreactor/config.ini
touch .pioreactor/unit_config.ini
```

Do not commit `.envrc`, `.pioreactor/`, `plugins_dev/`, or generated local state.

## 4. Configure direnv

Create a local `.envrc`:

```bash
export TESTING=1
export HOSTNAME=localhost
export ACTIVE=1

export DOT_PIOREACTOR="$PWD/.pioreactor"
export GLOBAL_CONFIG="$DOT_PIOREACTOR/config.ini"
export RUN_PIOREACTOR="$DOT_PIOREACTOR"
export PLUGINS_DEV="$PWD/plugins_dev"

export PIO_EXECUTABLE="$PWD/.venv/bin/pio"
export PIOS_EXECUTABLE="$PWD/.venv/bin/pios"
PATH_add "$PWD/.venv/bin"

export HARDWARE=1.1
export FIRMWARE=1.1
export MODEL_NAME=pioreactor_40ml
export MODEL_VERSION=1.5

export BLINKA_FORCECHIP=BCM2XXX
export BLINKA_FORCEBOARD=RASPBERRY_PI_4B
```

Allow it:

```bash
direnv allow
```

Check that the required variables are loaded:

```bash
make check-env
```

If you do not use `direnv`, export the same variables manually in every shell before running `make`, `pio`, or `pios`. Replace the `PATH_add` line with `export PATH="$PWD/.venv/bin:$PATH"`.

## 5. Install dependencies

Install Python dependencies and the editable `pio` / `pios` commands:

```bash
make install
```

Install frontend dependencies:

```bash
make frontend-install
```

Confirm the CLI is available:

```bash
command -v pio
pio version
```

If `command -v pio` prints nothing, reload the shell or run:

```bash
direnv reload
```

You can always run the CLI directly as:

```bash
.venv/bin/pio version
```

## 6. Start MQTT for local UI work

Many pages still load without MQTT, but live job state, charts, and browser MQTT subscriptions need a local broker. Use this small dev config:

```bash
mkdir -p scratch
cat > scratch/mosquitto-dev.conf <<'EOF'
listener 1883 127.0.0.1
allow_anonymous true

listener 9001 127.0.0.1
protocol websockets
allow_anonymous true
EOF
```

Start Mosquitto in its own terminal:

```bash
mosquitto -c scratch/mosquitto-dev.conf
```

Leave it running while using the web UI.

## 7. Start the dev services

First ask the Makefile what is already running:

```bash
make dev-status
```

Start only the services listed under `Need to start`. In separate terminals:

```bash
make huey-dev
```

```bash
make web-dev
```

```bash
make frontend-dev
```

The web API listens on `http://127.0.0.1:4999`. The React dev server listens on `http://localhost:3000` and proxies API requests to `http://localhost:4999`.

Open:

```text
http://localhost:3000
```

## 8. Verify the setup

Run these checks from the repo root:

```bash
make dev-status
pio version
pio workers
curl -fsS http://127.0.0.1:4999/unit_api/health
```


## Common problems

### `pio` is not found

The `pio` command is created by `make install` when it installs `core/` in editable mode. Run:

```bash
PYTHON=python3.13 make install
direnv reload
command -v pio
```

Or use `.venv/bin/pio` directly.

### Frontend starts but API calls fail

Make sure the Flask API is running:

```bash
make dev-status
```

If `Flask web API` is missing, start:

```bash
make web-dev
```
