# SBR (Simple Backup and Restore)

SBR is a simple deployment and backup manager for your projects.

## Installation

Run the following command on your Linux machine:

~~~bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/VerumHades/sbr/main/install.sh)"
~~~

This will:

1. Download the latest `sbr` Python script.  
2. Make it executable.  
3. Place it in `/usr/local/bin` so you can run it from anywhere.

## Usage

After installation, you can run:

~~~bash
sbr register myalias /path/to/repo
sbr backup myalias
sbr restore myalias
sbr deploy myalias
~~~

Replace `myalias` with your repository alias.