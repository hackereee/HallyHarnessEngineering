from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from . import __version__
from .installer import InstallMode, check_harness, install_harness


def print_operations(operations: Iterable[object]) -> None:
    for operation in operations:
        print(f"{operation.action} {operation.path}")


def run_install(args: argparse.Namespace, mode: InstallMode) -> int:
    result = install_harness(args.target, mode=mode, dry_run=args.dry_run)
    if args.dry_run:
        print_operations(result.operations)
    else:
        print(f"copied {result.copy_count}, pruned {result.prune_count}")
    return 0


def run_check(args: argparse.Namespace) -> int:
    report = check_harness(args.target)
    if report.ok:
        print("ok")
        return 0
    for asset in report.missing_assets:
        print(f"missing {asset}")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hally-harness-engineering",
        description="Install or update Harness Engineering runtime assets",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", help="Install Harness assets into a target repository")
    install.add_argument("target", type=Path, help="Target repository root")
    install.add_argument("--dry-run", action="store_true", help="Print planned operations without writing")

    update = subparsers.add_parser("update", help="Update Harness assets in a target repository")
    update.add_argument("target", type=Path, help="Target repository root")
    update.add_argument("--dry-run", action="store_true", help="Print planned operations without writing")

    check = subparsers.add_parser("check", help="Check whether fixed Harness assets are present")
    check.add_argument("target", type=Path, help="Target repository root")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.command == "install":
        return run_install(args, InstallMode.INSTALL)
    if args.command == "update":
        return run_install(args, InstallMode.UPDATE)
    if args.command == "check":
        return run_check(args)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
