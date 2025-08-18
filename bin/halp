#!/bin/bash
# halp_wrapper.sh - A wrapper script for the halp Python tool

# Set the project directory to the actual location
PROJECT_DIR="/Users/satoshi/Downloads/halp"

# Activate the virtual environment
if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
fi

# Run the Python script with all arguments passed to this script
python "$PROJECT_DIR/halp.py" "$@"

# Deactivate the virtual environment if it was activated
if type deactivate >/dev/null 2>&1; then
    deactivate
fi
