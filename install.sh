#!/bin/bash
# Installation script for halp

set -e

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p ~/bin bin

# Make sure the shell script is executable
echo "Setting permissions..."
chmod +x bin/halp

# Install Python dependencies
echo "Installing Python dependencies..."
if [ -d "venv" ]; then
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
else
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
fi

# Create the wrapper script with the absolute path
echo "Creating wrapper script..."
sed "s|PROJECT_DIR=\".*\"|PROJECT_DIR=\"$(pwd)\"|" bin/halp_wrapper.sh > bin/halp_wrapper_configured.sh
chmod +x bin/halp_wrapper_configured.sh

# Copy the wrapper script to ~/bin
echo "Installing to ~/bin..."
cp bin/halp_wrapper_configured.sh ~/bin/halp

# Check if ~/bin is in PATH
if [[ ":$PATH:" != *":$HOME/bin:"* ]]; then
    echo "Warning: ~/bin is not in your PATH. You may need to add it."
    echo "Add the following line to your shell profile (.bashrc, .zshrc, etc.):"
    echo "export PATH=\$HOME/bin:\$PATH"
fi

echo "Installation complete! You can now use 'halp' from the command line."
