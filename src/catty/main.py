#!/usr/bin/env python3
"""Catty - Unified application & game categorizer for Walker, Vicinae, and Spot."""

import argparse
import hashlib
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

from .backends import resolve_targets
from .backends.spot import SpotBackend
from .categorizer import AppCategorizer
from .config import (
    DEFAULT_CATEGORIES,
    DEFAULT_TARGET,
    PROVIDER,
    REVERSE_CATEGORY_MAPPING,
    STATE_FILE,
    XDG_CONFIG_HOME,
)
from .parser import DesktopEntry, DesktopFileParser
from .writer import DesktopFileWriter

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _map_desktop_category(entry: DesktopEntry) -> Optional[str]:
    if entry.is_obvious_game():
        return "Games"
    if "WebBrowser" in entry.categories:
        return "Browser"
    for cat in entry.categories:
        if cat in REVERSE_CATEGORY_MAPPING:
            return REVERSE_CATEGORY_MAPPING[cat]
    return None


def _compute_fingerprint(entries: Dict[str, DesktopEntry]) -> str:
    items = sorted(
        f"{fname}:{','.join(sorted(e.categories))}:{e.name}" for fname, e in entries.items()
    )
    return hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()


def cmd_scan(args) -> int:
    parser = DesktopFileParser()
    entries = parser.scan_all()

    if args.uncategorized:
        entries = {f: e for f, e in entries.items() if not _map_desktop_category(e)}
    elif args.category:
        entries = {
            f: e
            for f, e in entries.items()
            if _map_desktop_category(e) == args.category or args.category in e.categories
        }

    print(f"Found {len(entries)} application(s):\n")
    for i, (filename, entry) in enumerate(entries.items(), 1):
        if args.limit and i > args.limit:
            print(f"... and {len(entries) - args.limit} more")
            break
        mapped = _map_desktop_category(entry) or "(uncategorized)"
        print(f"{i}. {entry.name} [{mapped}] ({filename})")
    return 0


def cmd_categorize(args) -> int:
    parser = DesktopFileParser()
    entries = parser.scan_all()

    if args.recategorize:
        target_entries = entries
    else:
        target_entries = {f: e for f, e in entries.items() if not _map_desktop_category(e)}

    if not target_entries:
        logger.info("All applications already have valid categories.")
        return 0

    if args.limit:
        target_entries = dict(list(target_entries.items())[: args.limit])

    try:
        categorizer = AppCategorizer(
            provider=args.provider,
            model=args.model,
            local_url=args.local_url,
        )
    except Exception as e:
        logger.error(str(e))
        return 1

    categorization = categorizer.categorize(target_entries, batch_size=args.batch_size)
    if not categorization:
        logger.error("Categorization returned no results.")
        return 1

    print(f"\nCategorized {len(categorization)} application(s):")
    for filename, category in categorization.items():
        entry = target_entries[filename]
        old_cats = ", ".join(entry.categories) if entry.categories else "None"
        print(f"  - {entry.name}: {old_cats} -> {category}")

    if args.dry_run:
        print("\n[DRY RUN] No files modified.")
        return 0

    if not args.yes:
        confirm = input("\nApply changes to ~/.local/share/applications? [y/N] ")
        if confirm.strip().lower() != "y":
            print("Cancelled.")
            return 0

    writer = DesktopFileWriter(dry_run=False)
    results = writer.apply_categorization(target_entries, categorization)
    ok = sum(1 for v in results.values() if v)
    print(f"Updated {ok}/{len(results)} .desktop files (backup: {writer.backup_timestamp}).")
    return 0


def cmd_deps(args) -> int:
    backends = resolve_targets(args.target)
    all_ok = True
    for backend in backends:
        missing_req, _ = backend.check_dependencies()
        status = "OK" if not missing_req else "MISSING REQUIRED"
        print(f"[{backend.name}] {status}")
        for dep in backend.dependencies:
            mark = "OK" if dep.is_installed() else ("MISSING" if dep.required else "optional")
            kind = "req" if dep.required else "opt"
            print(f"  - {dep.binary:<10} [{mark:<8}] ({kind}) pkg={dep.package}  {dep.url}")
        if missing_req:
            all_ok = False
    return 0 if all_ok else 1


def cmd_menus(args) -> int:
    backends = resolve_targets(args.target)
    if args.clean:
        ok = True
        for backend in backends:
            if not backend.cleanup(restart=not args.no_restart):
                ok = False
            elif not args.quiet:
                print(f"Cleaned generated menus for {backend.name}.")
        return 0 if ok else 1

    if not args.dry_run and not args.ignore_deps:
        missing_any = False
        for backend in backends:
            missing_req, missing_opt = backend.check_dependencies()
            if missing_req:
                missing_any = True
                details = ", ".join(f"{d.binary} (pkg: {d.package}, {d.url})" for d in missing_req)
                logger.error(
                    f"Missing required launcher dependency for '{backend.name}': {details}. "
                    "Install it or pass --ignore-deps."
                )
            elif missing_opt and not args.quiet:
                opt_names = ", ".join(f"{d.binary} ({d.package})" for d in missing_opt)
                logger.info(f"Optional tools missing for '{backend.name}': {opt_names}")
        if missing_any:
            return 1

    parser = DesktopFileParser()
    entries = parser.scan_all()

    categorized: Dict[str, str] = {}
    uncategorized_count = 0
    for filename, entry in entries.items():
        cat = _map_desktop_category(entry)
        if cat:
            categorized[filename] = cat
        else:
            uncategorized_count += 1

    if not categorized:
        logger.error("No categorized applications found. Run 'catty categorize --yes' first.")
        return 1

    if uncategorized_count > 0 and not args.quiet:
        logger.info(
            f"{uncategorized_count} uncategorized app(s) skipped (run 'catty categorize -y' to classify)."
        )

    ok = True
    for backend in backends:
        if not backend.generate(
            categorized,
            entries,
            dry_run=args.dry_run,
            restart=not args.no_restart and not args.dry_run,
        ):
            ok = False
        elif not args.quiet and not args.dry_run:
            print(f"Generated {backend.name} category menus.")
    return 0 if ok else 1


def cmd_auto(args) -> int:
    """Automated non-interactive categorize + menu sync with loop guard."""
    backends = resolve_targets(args.target)
    parser = DesktopFileParser()
    entries = parser.scan_all()
    fp = _compute_fingerprint(entries)

    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    if (
        not args.force
        and state.get("fingerprint") == fp
        and all(b.output_exists() for b in backends)
    ):
        return 0

    uncategorized = {f: e for f, e in entries.items() if not _map_desktop_category(e)}
    if uncategorized:
        try:
            categorizer = AppCategorizer(provider=args.provider, model=args.model)
            categorization = categorizer.categorize(uncategorized)
            if categorization:
                writer = DesktopFileWriter(dry_run=False)
                writer.apply_categorization(uncategorized, categorization)
                entries = parser.scan_all()
                fp = _compute_fingerprint(entries)
        except Exception as e:
            logger.warning(f"Auto-categorization skipped ({e}); syncing existing categories.")

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"fingerprint": fp}), encoding="utf-8")

    categorized = {
        f: cat for f, e in entries.items() if (cat := _map_desktop_category(e)) is not None
    }
    if categorized:
        for backend in backends:
            backend.generate(categorized, entries, dry_run=False, restart=True)
    return 0


def cmd_service(args) -> int:
    systemd_dir = XDG_CONFIG_HOME / "systemd/user"
    systemd_dir.mkdir(parents=True, exist_ok=True)
    repo_dir = Path(__file__).resolve().parents[2]
    catty_bin = repo_dir / "catty"
    exec_bin = str(catty_bin) if catty_bin.exists() else "catty"

    units = {
        "catty-watcher.path": """[Unit]
Description=Watch application directories for new games/apps (Catty)

[Path]
PathChanged=/usr/share/applications
PathChanged=%h/.local/share/applications
Unit=catty-sync.service

[Install]
WantedBy=default.target
""",
        "catty-sync.timer": """[Unit]
Description=Periodic Catty category & usage sync timer

[Timer]
OnBootSec=2min
OnUnitActiveSec=30min
Persistent=true
Unit=catty-sync.service

[Install]
WantedBy=timers.target
""",
        "catty-sync.service": f"""[Unit]
Description=Catty automatic app categorizer and launcher menu generator

[Service]
Type=oneshot
ExecStart={exec_bin} auto --target {args.target}
""",
    }

    if args.action == "install":
        for name, content in units.items():
            (systemd_dir / name).write_text(content, encoding="utf-8")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", "catty-watcher.path", "catty-sync.timer"],
            check=True,
        )
        print("Installed and enabled catty-watcher.path and catty-sync.timer.")
        return 0
    if args.action == "uninstall":
        subprocess.run(
            ["systemctl", "--user", "disable", "--now", "catty-watcher.path", "catty-sync.timer"],
            check=False,
        )
        print("Disabled catty systemd units.")
        return 0

    subprocess.run(
        ["systemctl", "--user", "status", "catty-watcher.path", "catty-sync.timer", "--no-pager"],
        check=False,
    )
    return 0


def cmd_rollback(args) -> int:
    writer = DesktopFileWriter()
    if args.list:
        for i, b in enumerate(writer.list_backups(), 1):
            print(f"  {i}. {b}")
        return 0
    return 0 if writer.rollback(args.timestamp) else 1


def cmd_categories(_args) -> int:
    for i, c in enumerate(DEFAULT_CATEGORIES, 1):
        print(f"  {i}. {c}")
    return 0


def cmd_spot_query(args) -> int:
    rows = SpotBackend().query_rows(" ".join(args.query))
    for row in rows:
        print(row)
    return 0


def cmd_spot_launch(args) -> int:
    return SpotBackend().launch_selection(" ".join(args.app))


def cmd_spot_open(args) -> int:
    return SpotBackend().open_category(" ".join(args.category))


def main(default_target: Optional[str] = None, argv: Optional[list[str]] = None) -> int:
    target_default = default_target or DEFAULT_TARGET
    parser = argparse.ArgumentParser(
        description="Catty - Unified app & game categorizer for Walker, Vicinae, and Spot"
    )
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="Scan .desktop applications")
    p_scan.add_argument("-u", "--uncategorized", action="store_true")
    p_scan.add_argument("-c", "--category", type=str)
    p_scan.add_argument("-l", "--limit", type=int)

    p_cat = sub.add_parser("categorize", help="Categorize apps via Local or Cloud LLM")
    p_cat.add_argument("--dry-run", action="store_true")
    p_cat.add_argument("-y", "--yes", "--apply", action="store_true", dest="yes")
    p_cat.add_argument("-r", "--recategorize", action="store_true")
    p_cat.add_argument("-l", "--limit", type=int)
    p_cat.add_argument("-b", "--batch-size", type=int, default=30)
    p_cat.add_argument("--provider", choices=["auto", "local", "cloud"], default=PROVIDER)
    p_cat.add_argument("--model", type=str, default=None)
    p_cat.add_argument("--local-url", type=str, default="http://127.0.0.1:11434")

    p_menu = sub.add_parser("menus", help="Generate launcher category menus/extensions")
    p_menu.add_argument(
        "-t", "--target", choices=["auto", "spot", "vicinae", "walker", "all"], default=target_default
    )
    p_menu.add_argument("--dry-run", action="store_true")
    p_menu.add_argument("--clean", action="store_true")
    p_menu.add_argument("-q", "--quiet", action="store_true")
    p_menu.add_argument("--no-restart", action="store_true")
    p_menu.add_argument("--ignore-deps", action="store_true")

    p_deps = sub.add_parser("deps", aliases=["check"], help="Check external launcher tool dependencies")
    p_deps.add_argument(
        "-t", "--target", choices=["auto", "spot", "vicinae", "walker", "all"], default=target_default
    )

    p_auto = sub.add_parser("auto", help="Non-interactive categorize + menu sync")
    p_auto.add_argument(
        "-t", "--target", choices=["auto", "spot", "vicinae", "walker", "all"], default=target_default
    )
    p_auto.add_argument("-f", "--force", action="store_true")
    p_auto.add_argument("--provider", choices=["auto", "local", "cloud"], default=PROVIDER)
    p_auto.add_argument("--model", type=str, default=None)

    p_svc = sub.add_parser("service", help="Manage systemd user watcher & timer")
    p_svc.add_argument("action", choices=["install", "uninstall", "status"], default="status", nargs="?")
    p_svc.add_argument(
        "-t", "--target", choices=["auto", "spot", "vicinae", "walker", "all"], default=target_default
    )

    p_rb = sub.add_parser("rollback", help="Rollback .desktop file changes")
    p_rb.add_argument("-l", "--list", action="store_true")
    p_rb.add_argument("-t", "--timestamp", type=str)

    sub.add_parser("categories", help="List supported categories")

    p_sq = sub.add_parser("spot-query", help=argparse.SUPPRESS)
    p_sq.add_argument("query", nargs="*")

    p_sl = sub.add_parser("spot-launch", help=argparse.SUPPRESS)
    p_sl.add_argument("app", nargs="+")

    p_so = sub.add_parser("spot-open", help=argparse.SUPPRESS)
    p_so.add_argument("category", nargs="+")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    dispatch = {
        "scan": cmd_scan,
        "categorize": cmd_categorize,
        "menus": cmd_menus,
        "deps": cmd_deps,
        "check": cmd_deps,
        "auto": cmd_auto,
        "service": cmd_service,
        "rollback": cmd_rollback,
        "categories": cmd_categories,
        "spot-query": cmd_spot_query,
        "spot-launch": cmd_spot_launch,
        "spot-open": cmd_spot_open,
    }
    return dispatch[args.command](args)


def main_walker() -> int:
    return main(default_target="walker")


def main_vicinae() -> int:
    return main(default_target="vicinae")


def main_spot() -> int:
    return main(default_target="spot")


if __name__ == "__main__":
    sys.exit(main())
