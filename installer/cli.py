from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .engine import Installer, InstallerError
from .model import InstallContext


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="install.sh",
        description="Fedora Nova Installer V2 safe host reinstall/upgrade tool",
    )
    action = result.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--dry-run",
        action="store_true",
        help="discover host state and print the install plan without writing anything",
    )
    action.add_argument(
        "--install",
        action="store_true",
        help="back up and install the current checkout into the user host",
    )
    action.add_argument(
        "--validate",
        action="store_true",
        help="validate the current Installer V2 host installation",
    )
    action.add_argument(
        "--rollback",
        metavar="BACKUP",
        type=Path,
        help="restore one Installer V2 backup",
    )
    action.add_argument(
        "--uninstall",
        action="store_true",
        help="back up and remove only manifest-owned Fedora Nova files",
    )
    action.add_argument(
        "--uninstall-dry-run",
        action="store_true",
        help="show manifest-owned files that a V2 uninstall would remove",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    source_root = Path(__file__).resolve().parents[1]
    try:
        context = InstallContext.from_environ(source_root)
        installer = Installer(context)
        if args.dry_run:
            installer.dry_run()
            return 0
        if args.install:
            installer.install()
            return 0
        if args.validate:
            return 0 if installer.validate().ok else 1
        if args.rollback:
            installer.rollback(args.rollback)
            return 0
        if args.uninstall:
            installer.uninstall()
            return 0
        if args.uninstall_dry_run:
            installer.uninstall(dry_run=True)
            return 0
    except InstallerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ERROR: interrupted; no automatic rollback was attempted.", file=sys.stderr)
        return 130
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
