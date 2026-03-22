#!/usr/bin/env python3

import argparse
import os
import subprocess
from datetime import datetime
from pathlib import Path

# Configuration Constants
CONFIG_DIRECTORY = Path.home() / ".deploy_manager"
REGISTRY_FILE = CONFIG_DIRECTORY / "repositories.txt"
DEFAULT_BACKUP_ROOT = Path.home() / ".backup"


def ensure_configuration_exists():
    """Initializes the configuration directory and registry file."""
    CONFIG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_FILE.exists():
        REGISTRY_FILE.touch()


def get_registered_repositories():
    """Reads the registry and returns a mapping of aliases to Path objects."""
    ensure_configuration_exists()
    repositories = {}
    with REGISTRY_FILE.open("r") as file_handle:
        for line in file_handle:
            clean_line = line.strip()
            if clean_line:
                alias, path_string = clean_line.split("|", 1)
                repositories[alias] = Path(path_string)
    return repositories


def save_repository_registration(alias, repository_path):
    """Persists a new repository alias and path to the registry."""
    ensure_configuration_exists()
    with REGISTRY_FILE.open("a") as file_handle:
        file_handle.write(f"{alias}|{repository_path}\n")


def execute_shell_command(command_parts, working_directory=None):
    """
    Executes a system command. 
    Attempts elevation via sudo if initial permission is denied.
    """
    try:
        subprocess.run(command_parts, check=True, cwd=working_directory)
    except subprocess.CalledProcessError as error:
        if error.returncode in [1, 13]:
            print("Permission denied. Retrying with sudo...")
            elevated_command = ["sudo"] + command_parts
            subprocess.run(elevated_command, check=True, cwd=working_directory)
        else:
            raise


def extract_database_url(repository_path):
    """Parses the .env file within the backend directory for DATABASE_URL."""
    env_file = repository_path / "backend" / ".env"
    if not env_file.exists():
        return None

    with env_file.open("r") as file_handle:
        for line in file_handle:
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    return None


def backup_database(repository_path, backup_destination):
    """Detects database type and creates a SQL dump inside the backup folder."""
    database_url = extract_database_url(repository_path)
    if not database_url:
        return

    output_file = backup_destination / "database.sql"
    if database_url.startswith("mysql"):
        execute_shell_command(["mysqldump", database_url, f"--result-file={output_file}"])
    elif database_url.startswith("postgres"):
        execute_shell_command(["pg_dump", database_url, "-f", str(output_file)])


def perform_rsync_backup(source_path, destination_path):
    """Executes rsync to copy project files, excluding transient directories."""
    exclude_list = [
        "--exclude=.git", "--exclude=node_modules", "--exclude=vendor",
        "--exclude=var/cache", "--exclude=var/log"
    ]
    rsync_command = ["rsync", "-a", "--delete"] + exclude_list + [f"{source_path}/", str(destination_path)]
    execute_shell_command(rsync_command)


def create_project_backup(repository_path, backup_root):
    """Orchestrates the full file and database backup process."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"{repository_path.name}_{timestamp}"
    
    backup_root.mkdir(parents=True, exist_ok=True)
    
    perform_rsync_backup(repository_path, backup_path)
    backup_database(repository_path, backup_path)
    
    print(f"Backup created at: {backup_path}")
    return backup_path


def get_current_git_branch(repository_path):
    """Returns the name of the currently active git branch."""
    output = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repository_path
    )
    return output.decode().strip()


def sync_git_repository(repository_path):
    """Fetches remote changes and hard resets the local branch to match origin."""
    execute_shell_command(["git", "fetch", "origin"], repository_path)
    current_branch = get_current_git_branch(repository_path)
    execute_shell_command(["git", "reset", "--hard", f"origin/{current_branch}"], repository_path)


def build_frontend_assets(repository_path):
    """Runs npm install and production build for the frontend."""
    frontend_path = repository_path / "frontend"
    if frontend_path.exists():
        execute_shell_command(["npm", "install"], frontend_path)
        execute_shell_command(["npm", "run", "build"], frontend_path)


def build_backend_application(repository_path):
    """Runs composer install and doctrine migrations for the backend."""
    backend_path = repository_path / "backend"
    if backend_path.exists():
        composer_cmd = ["composer", "install", "--no-dev", "--optimize-autoloader"]
        execute_shell_command(composer_cmd, backend_path)
        
        migration_cmd = ["php", "bin/console", "doctrine:migrations:migrate", "--no-interaction"]
        execute_shell_command(migration_cmd, backend_path)


def command_register(args):
    """CLI: Registers a new repository alias."""
    alias = args.alias
    repository_path = Path(args.path or os.getcwd()).resolve()
    save_repository_registration(alias, repository_path)
    print(f"Registered '{alias}' at {repository_path}")


def command_list(args):
    """CLI: Lists all registered repositories."""
    repositories = get_registered_repositories()
    for alias, path in repositories.items():
        print(f"{alias} -> {path}")


def command_backup(args):
    """CLI: Manually triggers a backup."""
    repositories = get_registered_repositories()
    path = repositories.get(args.alias)
    if not path:
        print(f"Alias '{args.alias}' not found.")
        return

    create_project_backup(path, Path(args.backup_root))


def command_restore(args):
    """CLI: Restores a repository from a selected backup."""
    repositories = get_registered_repositories()
    path = repositories.get(args.alias)
    if not path:
        print(f"Alias '{args.alias}' not found.")
        return

    backup_root = Path(args.backup_root)
    backups = sorted([p for p in backup_root.iterdir() if p.name.startswith(f"{path.name}_")])

    if not backups:
        print("No backups available.")
        return

    for index, backup in enumerate(backups):
        print(f"[{index}] {backup.name}")

    selection = input("Select backup index: ").strip()
    if selection.isdigit() and int(selection) < len(backups):
        selected_backup = backups[int(selection)]
        execute_shell_command(["rsync", "-a", "--delete", f"{selected_backup}/", str(path)])
        print("Restore completed.")
    else:
        print("Invalid selection.")


def command_deploy(args):
    """CLI: Orchestrates the full backup and deployment sequence."""
    repositories = get_registered_repositories()
    path = repositories.get(args.alias)
    if not path:
        print(f"Alias '{args.alias}' not found.")
        return

    create_project_backup(path, Path(args.backup_root))
    sync_git_repository(path)
    build_frontend_assets(path)
    build_backend_application(path)
    
    execute_shell_command(["systemctl", "restart", "caddy"])
    print("Deployment successfully finished.")


def build_argument_parser():
    """Defines the CLI structure and subcommands."""
    parser = argparse.ArgumentParser(description="Deployment Manager")
    subparsers = parser.add_subparsers(dest="command")

    reg = subparsers.add_parser("register")
    reg.add_argument("alias")
    reg.add_argument("path", nargs='?')
    reg.set_defaults(func=command_register)

    subparsers.add_parser("list").set_defaults(func=command_list)

    back = subparsers.add_parser("backup")
    back.add_argument("alias")
    back.add_argument("--backup-root", default=str(DEFAULT_BACKUP_ROOT))
    back.set_defaults(func=command_backup)

    rest = subparsers.add_parser("restore")
    rest.add_argument("alias")
    rest.add_argument("--backup-root", default=str(DEFAULT_BACKUP_ROOT))
    rest.set_defaults(func=command_restore)

    depl = subparsers.add_parser("deploy")
    depl.add_argument("alias")
    depl.add_argument("--backup-root", default=str(DEFAULT_BACKUP_ROOT))
    depl.set_defaults(func=command_deploy)

    return parser


def main():
    parser = build_argument_parser()
    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()