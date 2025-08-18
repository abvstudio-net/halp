# halp

`halp` is a command line tool that provides remote-Ollama assistance for the command line.

It connects to your remote Ollama instances (via OpenAI-compatible API) and injects contextual information into prompts, helping the LLM understand exactly what you're working with.

## Installation

1. git clone this repo

```
cd halp
chmod +x ./halp
mkdir -p ~/.local/bin
mv ./halp ~/.local/bin/halp
touch ~/.halp.yaml
```

```sh
# Add ~/.local/bin to PATH for zsh on macOS
if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' ~/.zshrc; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
fi
source ~/.zshrc
```

## Usage

```bash
# Basic usage
halp "How do I implement a binary search in Python?"

# Specify a different Ollama model
halp --model llama3 "Explain the difference between promises and async/await in JavaScript"

# Connect to a remote Ollama instance
halp --host remote-ollama.example.com:11434 "What's wrong with my Docker configuration?"
```

## Configuration

You can configure `halp` by creating a config file at `~/.halp.yaml`:

```yaml
host: localhost:11434
api_key: your_api_key_here

# Default model to use
model: gemma3

# Additional context settings
context:
  include_git: true  # Include git information in context
  max_files: 5       # Maximum number of files to include in context
```
