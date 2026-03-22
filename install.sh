#!/usr/bin/env bash

# Change these URLs to your hosted script location
SCRIPT_URL="https://yourdomain.com/deploy_manager.py"
INSTALL_DIR="/usr/local/bin"
SCRIPT_NAME="deploy_manager"

# Download the script
curl -fsSL "$SCRIPT_URL" -o "$INSTALL_DIR/$SCRIPT_NAME"

# Make it executable
chmod +x "$INSTALL_DIR/$SCRIPT_NAME"

echo "Installation complete! You can now run '$SCRIPT_NAME' from anywhere."