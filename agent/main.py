"""Backup agent CLI entry point (PRD section 5.1).

Runs a single backup, reports the result to the Backup API, applies retention
pruning, and returns an appropriate exit code (0 = success, 1 = failure).
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the agent CLI.

    Returns:
        A configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        prog="backup-agent", description="Run a centralized database backup"
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run one backup and report the result")
    run_parser.add_argument("--report", action="store_true", help="Report result to the Backup API")

    prune_parser = subparsers.add_parser("prune", help="Delete backups older than retention")
    prune_parser.add_argument(
        "--report", action="store_true", help="Report the prune summary (no-op in MVP)"
    )
    return parser


def run_backup(report: bool) -> int:
    """Execute one backup cycle.

    Args:
        report: Whether to report the result to the Backup API.

    Returns:
        Process exit code (0 success, 1 failure).
    """
    from agent.backup import BackupEngine, Reporter, cleanup
    from agent.config import get_config

    config = get_config()
    engine = BackupEngine(config)
    outcome = engine.run()
    cleanup(outcome.storage_path if outcome.status == "failed" else None)
    reachable = True
    if report:
        reachable = Reporter(config).report(outcome)
    return 0 if outcome.status == "success" and reachable else 1


def run_prune() -> int:
    """Prune expired backups from local storage.

    Returns:
        Process exit code (0).
    """
    from agent.backup import prune
    from agent.config import get_config

    config = get_config()
    removed = prune(config.retention_days, config.storage_base_dir)
    print(f"pruned {removed} expired backup(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch the agent subcommand and return an exit code.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        The process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "prune":
        return run_prune()
    if args.command == "run":
        return run_backup(args.report)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())