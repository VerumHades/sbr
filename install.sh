#!/usr/bin/env bash

# Change these URLs to your hosted script location
SCRIPT_URL="https://raw.githubusercontent.com/VerumHades/sbr/main/sbr.py"
INSTALL_DIR="/usr/local/bin"
SCRIPT_NAME="sbr"

# Download the script
curl -fsSL "$SCRIPT_URL" -o "$INSTALL_DIR/$SCRIPT_NAME"

chmod +x "$INSTALL_DIR/$SCRIPT_NAME"

echo "Installation complete! You can now run '$SCRIPT_NAME' from anywhere."