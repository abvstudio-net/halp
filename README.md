# halp

`halp` is a command line tool that provides AI assistance for your terminal workflows. It connects to an OpenAI-compatible endpoint (e.g., Open WebUI, OpenAI).

## Features

- Simple configuration via `~/.halp.env`
- OpenAI-compatible model listing via `/v1/models`
- CLI overrides for base URL, API key, and model
- Verbose and debug logging
- Secure config file permissions (0600)
- Interactive first-run setup

## Requirements

- Python 3.8+

## Configuration

`halp` stores configuration in `~/.halp.env`. If the file doesn’t exist, the CLI will guide you through a short setup:

```env
BASE_URL=
API_KEY=
DEFAULT_MODEL=
```

 

## Installation

Install (user-only) via pip:

```bash
python3 -m pip install --user .
```

Development (editable) install (user):

```bash
python3 -m pip install --user -e .
```

Note: Global/system-wide installs are not supported. Always use `--user` and do not use `sudo`.

## PATH notes

- Linux (and many macOS setups) will place user-installed scripts in `~/.local/bin`.
  - Ensure it’s on your PATH:
    ```bash
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    # For zsh:
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
    ```
- On some macOS Python installs, user scripts go to `$(python3 -m site --user-base)/bin`.
  - You can add it like this:
    ```bash
    echo "export PATH=\"$(python3 -m site --user-base)/bin:\$PATH\"" >> ~/.zshrc
    ```

## Where it gets installed

- CLI script: `~/.local/bin/halp` (with `--user` installs)
- Module: `~/.local/lib/pythonX.Y/site-packages/halp.py`
- Metadata: `~/.local/lib/pythonX.Y/site-packages/halp-<version>.dist-info/`
  - License is included here
  - README contents are embedded in `METADATA`

## Quick start

Ensure pipx is installed

```sh
sudo apt install -y pipx
pipx ensurepath
#restart shell
pipx install git+https://github.com/ABVStudio-net/halp.git
```


## Usage

- Print help:
  ```bash
  halp --help
  ```
- Interactive setup:
  ```bash
  halp --init
  ```
- Print current configuration:
  ```bash
  halp --print-config
  ```
- List available models from the configured endpoint:
  ```bash
  halp -l
  ```
- Override model for a single run:
  ```bash
  halp -m hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q8_K_XL
  ```

## Development

- Editable install during development:
  ```bash
  pipx install --editable .
  ```
- Uninstall:
  ```bash
  pipx uninstall halp
  ```
