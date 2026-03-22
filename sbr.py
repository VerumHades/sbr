#!/usr/bin/env python3

import os
import subprocess
from datetime import datetime
from pathlib import Path
import argparse

CONFIG_PATH = Path.home() / ".deploy_manager"
REPOSITORIES_FILE = CONFIG_PATH / "repositories.txt"
DEFAULT_BACKUP_ROOT = Path("~/.backup")


def ensure_config_directory_exists():
    CONFIG_PATH.mkdir(parents=True, exist_ok=True)
    if not REPOSITORIES_FILE.exists():
        REPOSITORIES_FILE.touch()


def read_registered_repositories():
    ensure_config_directory_exists()
    repositories = {}
    with open(REPOSITORIES_FILE, "r") as file_handle:
        for line in file_handle:
            if line.strip():
                alias, path = line.strip().split("|", 1)
                repositories[alias] = path
    return repositories


def write_repository(alias, repository_path):
    ensure_config_directory_exists()
    with open(REPOSITORIES_FILE, "a") as file_handle:
        file_handle.write(f"{alias}|{repository_path}\n")

def run_command_with_elevation(command_parts, working_directory=None):
    """
    Runs a shell command. If it fails due to permission denied, asks for elevation.
    """
    try:
        subprocess.run(command_parts, check=True, cwd=working_directory)
    except subprocess.CalledProcessError as e:
        if e.returncode == 1 or e.returncode == 13:  # 13 = Permission denied
            print("Command failed due to permission issues. Trying with sudo...")
            sudo_command = ["sudo"] + command_parts
            subprocess.run(sudo_command, check=True, cwd=working_directory)
        else:
            raise

def run_command_with_elevation(command_parts, working_directory=None):
    subprocess.run(command_parts, check=True, cwd=working_directory)


def create_backup(repository_path, backup_root):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_name = repository_path.name
    backup_path = backup_root / f"{project_name}_{timestamp}"

    backup_root.mkdir(parents=True, exist_ok=True)

    run_command_with_elevation([
        "rsync", "-a", "--delete",
        "--exclude=.git",
        "--exclude=node_modules",
        "--exclude=vendor",
        "--exclude=var/cache",
        "--exclude=var/log",
        f"{repository_path}/",
        str(backup_path)
    ])

    env_path = repository_path / "backend/.env"
    if env_path.exists():
        database_url = None
        with open(env_path) as file_handle:
            for line in file_handle:
                if line.startswith("DATABASE_URL="):
                    database_url = line.split("=", 1)[1].strip()
                    break

        if database_url:
            if database_url.startswith("mysql"):
                run_command_with_elevation(["bash", "-c", f"mysqldump '{database_url}' > '{backup_path}/database.sql'"])
            elif database_url.startswith("postgres"):
                run_command_with_elevation(["bash", "-c", f"pg_dump '{database_url}' > '{backup_path}/database.sql'"])

    print(f"Backup created at {backup_path}")


def list_backups(repository_path, backup_root):
    project_name = repository_path.name
    if not backup_root.exists():
        return []

    backups = [
        path for path in backup_root.iterdir()
        if path.is_dir() and path.name.startswith(project_name + "_")
    ]

    return sorted(backups)


def command_register(args):
    """Register a new repository with an alias.

Positional arguments:
  alias        The alias name for the repository
  path         The full path to the repository (optional, defaults to current directory)"""
    alias = args.alias
    repository_path = args.path or os.getcwd()

    write_repository(alias, repository_path)
    print(f"Repository '{alias}' registered for path {repository_path}.")


def command_list(args):
    """List all registered repositories with their aliases."""
    repositories = read_registered_repositories()
    for alias, path in repositories.items():
        print(f"{alias} -> {path}")


def command_backup(args):
    """Create a backup of the repository specified by alias.

Positional arguments:
  alias        The alias of the repository to backup"""
    repositories = read_registered_repositories()
    repository_path = repositories.get(args.alias)
    if not repository_path:
        print(f"Alias '{args.alias}' not found.")
        return

    create_backup(Path(repository_path), Path(args.backup_root))


def command_restore(args):
    """Restore a repository from a backup.

Positional arguments:
  alias        The alias of the repository to restore"""
    repositories = read_registered_repositories()
    repository_path = repositories.get(args.alias)
    if not repository_path:
        print(f"Alias '{args.alias}' not found.")
        return

    backups = list_backups(Path(repository_path), Path(args.backup_root))
    if not backups:
        print("No backups available.")
        return

    print("Available backups:")
    for i, backup in enumerate(backups):
        print(f"[{i}] {backup}")
    selection = input("Select backup index: ").strip()
    if not selection.isdigit() or int(selection) >= len(backups):
        print("Invalid selection")
        return

    selected_backup = backups[int(selection)]
    run_command_with_elevation([
        "rsync", "-a", "--delete",
        f"{selected_backup}/",
        str(repository_path)
    ])
    print("Restore completed")


def command_deploy(args):
    """
        Deploy the repository specified by alias.
        Positional arguments:
        alias        The alias of the repository to deploy
    """
    repositories = read_registered_repositories()
    repository_path = repositories.get(args.alias)
    if not repository_path:
        print(f"Alias '{args.alias}' not found.")
        return

    repository_path = Path(repository_path)
    create_backup(repository_path, Path(args.backup_root))

    run_command_with_elevation(["git", "fetch", "origin"], repository_path)

    current_branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repository_path
    ).decode().strip()

    run_command_with_elevation(["git", "reset", "--hard", f"origin/{current_branch}"], repository_path)

    frontend_path = repository_path / "frontend"
    backend_path = repository_path / "backend"

    run_command_with_elevation(["npm", "install"], frontend_path)
    run_command_with_elevation(["npm", "run", "build"], frontend_path)

    run_command_with_elevation(["composer", "install", "--no-dev", "--optimize-autoloader"], backend_path)
    run_command_with_elevation(["php", "bin/console", "doctrine:migrations:migrate", "--no-interaction"], backend_path)

    run_command_with_elevation(["systemctl", "restart", "caddy"])
    print("Deployment completed")


def build_parser():
    parser = argparse.ArgumentParser(description="Deployment and Backup Manager")
    subparsers = parser.add_subparsers(dest="command")

    register_parser = subparsers.add_parser("register", help="Register a new repository with an alias")
    register_parser.add_argument("alias", help="Alias name for the repository")
    register_parser.add_argument("path", nargs='?', help="Repository path (optional, defaults to current directory)")
    register_parser.set_defaults(func=command_register)

    list_parser = subparsers.add_parser("list", help="List all registered repositories")
    list_parser.set_defaults(func=command_list)

    backup_parser = subparsers.add_parser("backup", help="Backup a repository using its alias")
    backup_parser.add_argument("alias", help="Alias of the repository to backup")
    backup_parser.add_argument("--backup-root", default=str(DEFAULT_BACKUP_ROOT), help="Root directory for backups")
    backup_parser.set_defaults(func=command_backup)

    restore_parser = subparsers.add_parser("restore", help="Restore a repository from backup using its alias")
    restore_parser.add_argument("alias", help="Alias of the repository to restore")
    restore_parser.add_argument("--backup-root", default=str(DEFAULT_BACKUP_ROOT), help="Root directory for backups")
    restore_parser.set_defaults(func=command_restore)

    deploy_parser = subparsers.add_parser("deploy", help="Deploy a repository using its alias")
    deploy_parser.add_argument("alias", help="Alias of the repository to deploy")
    deploy_parser.add_argument("--backup-root", default=str(DEFAULT_BACKUP_ROOT), help="Root directory for backups")
    deploy_parser.set_defaults(func=command_deploy)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()