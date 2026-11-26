"""Spot (SpottyCat) launcher backend: TOML category dialogs, collapsible tree, run bar & source."""

import json
import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

from ..config import SPOT_CATTY_DIR, SPOT_CONFIG_DIR, SPOT_FRECENCY_PATH
from ..parser import DesktopEntry
from .base import MenuBackend, ToolDep, clean_exec, group_and_sort

logger = logging.getLogger(__name__)


def _toml_str(value: str) -> str:
    return json.dumps(value)


class SpotBackend(MenuBackend):
    """Generates Spot (>= 0.7.0) TOML dialogs: categories, per-category lists, tree, quick bar, launcher."""

    name = "spot"
    dependencies = (
        ToolDep(
            binary="spot",
            package="spot-bin",
            url="https://github.com/KopyTKG/spot",
            required=True,
            purpose="Wayland dialog & launcher runtime (>= 0.7.0)",
        ),
        ToolDep(
            binary="qalc",
            package="libqalculate",
            url="https://qalculate.github.io",
            required=False,
            purpose="= calculator source in launcher.toml",
        ),
        ToolDep(
            binary="fd",
            package="fd",
            url="https://github.com/sharkdp/fd",
            required=False,
            purpose=". file search source in launcher.toml",
        ),
        ToolDep(
            binary="wl-copy",
            package="wl-clipboard",
            url="https://github.com/bugaevc/wl-clipboard",
            required=False,
            purpose="copy calculator/source output to clipboard",
        ),
        ToolDep(
            binary="gtk-launch",
            package="glib2",
            url="https://gitlab.gnome.org/GNOME/glib",
            required=False,
            purpose="launch .desktop entries by desktop id",
        ),
    )

    def __init__(
        self,
        output_dir: Path = SPOT_CATTY_DIR,
        frecency_path: Path = SPOT_FRECENCY_PATH,
        catty_cmd: str = "catty",
    ):
        self.output_dir = output_dir
        self.frecency_path = frecency_path
        self.catty_cmd = catty_cmd
        self.index_path = self.output_dir / "index.json"

    def is_available(self) -> bool:
        return bool(shutil.which("spot")) or SPOT_CONFIG_DIR.exists()

    def output_exists(self) -> bool:
        return self.index_path.exists()

    def _slug(self, category: str) -> str:
        return category.lower().replace(" ", "_")

    def _style_lines(self) -> List[str]:
        if (self.output_dir.parent / "spot.css").exists():
            return ['style = "../spot.css"']
        return []

    def _launch_templates(self) -> tuple[str, str]:
        cmd = "uwsm-app -- {exec}" if os.environ.get("UWSM_FINALIZE_VARNAMES") and shutil.which("uwsm-app") else "{exec}"
        if shutil.which("xdg-terminal-exec"):
            term = "xdg-terminal-exec {exec}"
        elif shutil.which("kitty"):
            term = "kitty -e {exec}"
        else:
            term = "xdg-terminal-exec {exec}"
        return cmd, term

    def get_usage_data(self) -> Dict[str, Dict]:
        """Read Spot frecency store ($XDG_STATE_HOME/spot/frecency.json)."""
        usage: Dict[str, Dict] = {}
        if not self.frecency_path.exists():
            return usage
        try:
            raw = json.loads(self.frecency_path.read_text(encoding="utf-8"))
            for app_id, stats in raw.items():
                if isinstance(stats, dict):
                    usage[f"{app_id}.desktop"] = {
                        "count": int(stats.get("count", 0)),
                        "last_used": int(stats.get("last", 0)),
                    }
        except Exception as e:
            logger.debug(f"Could not read Spot frecency.json: {e}")
        return usage

    def _build_cat_toml(self, category: str, app_names: List[str]) -> str:
        options = ", ".join(_toml_str(name) for name in app_names)
        cmd = f"{self.catty_cmd} spot-launch {{app}}"
        return "\n".join(
            [
                f"title = {_toml_str(category)}",
                'anchor = "top"',
                "margin_top = 120",
                "width = 560",
                *self._style_lines(),
                'keyboard = "exclusive"',
                'footer = "Enter to launch · Backspace/Esc to return"',
                "",
                "[[items]]",
                'type = "list"',
                'id = "app"',
                f"placeholder = {_toml_str(f'Search {category}…')}",
                'match = "smart"',
                "height = 360",
                f"options = [{options}]",
                "",
                "[submit]",
                f"exec = {_toml_str(cmd)}",
                "spawn = true",
                "",
            ]
        )

    def _build_categories_toml(self, cat_labels: List[str]) -> str:
        options = ", ".join(_toml_str(lbl) for lbl in cat_labels)
        cmd = f"{self.catty_cmd} spot-open {{category}}"
        return "\n".join(
            [
                'title = "Categories"',
                'anchor = "top"',
                "margin_top = 120",
                "width = 480",
                *self._style_lines(),
                "toggle = true",
                'keyboard = "exclusive"',
                'footer = "Enter to open · Esc to cancel"',
                "",
                "[back]",
                'show = "never"',
                "",
                "[[items]]",
                'type = "list"',
                'id = "category"',
                'placeholder = "Filter categories…"',
                'match = "smart"',
                "height = 320",
                f"options = [{options}]",
                "",
                "[submit]",
                f"exec = {_toml_str(cmd)}",
                "spawn = true",
                "",
            ]
        )

    def _build_grouped_toml(self, grouped_rows: List[str]) -> str:
        options = ", ".join(_toml_str(row) for row in grouped_rows)
        cmd = f"{self.catty_cmd} spot-launch {{app}}"
        return "\n".join(
            [
                'title = "Apps by Category"',
                'anchor = "top"',
                "margin_top = 120",
                "width = 580",
                *self._style_lines(),
                "toggle = true",
                'keyboard = "exclusive"',
                'footer = "Enter to expand/launch · Esc to cancel"',
                "",
                "[back]",
                'show = "auto"',
                "",
                "[[items]]",
                'type = "list"',
                'id = "app"',
                'placeholder = "Search apps or categories…"',
                "collapsible = true",
                "collapsed = true",
                'match = "smart"',
                "height = 400",
                f"options = [{options}]",
                "",
                "[submit]",
                f"exec = {_toml_str(cmd)}",
                "spawn = true",
                "",
            ]
        )

    def _build_quick_toml(self) -> str:
        """Spot v0.7.0 run-bar style instant category/app search (default source + hide_empty)."""
        return "\n".join(
            [
                'title = ""',
                'anchor = "top"',
                "margin_top = 160",
                "width = 640",
                *self._style_lines(),
                "toggle = true",
                'keyboard = "exclusive"',
                "",
                "[opacity]",
                "outside = 100",
                "",
                "[back]",
                'show = "never"',
                "",
                "[[items]]",
                'type = "apps"',
                'id = "app"',
                'placeholder = "Search categorized apps…"',
                "hide_empty = true",
                "",
                "[[sources]]",
                'name = "categories"',
                "default = true",
                'icon = "applications-other"',
                "min_chars = 1",
                f"exec = {_toml_str(f'{self.catty_cmd} spot-query {{query}}')}",
                f"activate = {_toml_str(f'{self.catty_cmd} spot-launch {{value}}')}",
                "",
            ]
        )

    def _build_launcher_toml(self) -> str:
        launch_cmd, terminal_cmd = self._launch_templates()
        return "\n".join(
            [
                'title = ""',
                'anchor = "top"',
                "margin_top = 120",
                "width = 640",
                *self._style_lines(),
                "toggle = true",
                'keyboard = "exclusive"',
                "",
                "[opacity]",
                "outside = 100",
                "",
                "[back]",
                'show = "never"',
                "",
                "[[items]]",
                'type = "apps"',
                'id = "app"',
                'placeholder = "Search apps…   # cat · = calc · . files · > run"',
                "height = 360",
                "",
                "[apps]",
                "show_comment = true",
                "max_results = 12",
                "frecency = true",
                "",
                "[apps.launch]",
                f"command = {_toml_str(launch_cmd)}",
                f"terminal = {_toml_str(terminal_cmd)}",
                "",
                "[[sources]]",
                'name = "categories"',
                'prefix = "#"',
                'icon = "applications-other"',
                "min_chars = 1",
                f"exec = {_toml_str(f'{self.catty_cmd} spot-query {{query}}')}",
                f"activate = {_toml_str(f'{self.catty_cmd} spot-launch {{value}}')}",
                "",
                "[[sources]]",
                'name = "calc"',
                'prefix = "="',
                'icon = "accessories-calculator"',
                'exec = "qalc -t -- {query} | head -n 1"',
                'activate = "wl-copy {value}"',
                "",
                "[[sources]]",
                'name = "files"',
                'prefix = "."',
                'icon = "system-file-manager"',
                """exec = "fd --max-results 40 -- {query} \\"$HOME\\" | awk '{ print $0 \\"\\\\t\\" $0 }'" """,
                'activate = "xdg-open {value}"',
                "",
                "[[sources]]",
                'name = "run"',
                'prefix = ">"',
                'icon = "utilities-terminal"',
                """exec = "bash -c 'compgen -c | sort -u | grep -i -m 30 -- \\"$0\\"' {query}" """,
                'activate = "sh -c {value}"',
                "",
            ]
        )

    def refresh_daemon(self) -> None:
        """Ask a running spot daemon to exit once idle so updated .desktop files are rescanned."""
        if not shutil.which("spot"):
            return
        try:
            status = subprocess.run(["spot", "--status"], capture_output=True, check=False)
            if status.returncode == 0:
                subprocess.run(["spot", "--quit"], capture_output=True, check=False)
                logger.info("Signaled spot daemon (--quit) to rescan .desktop entries on next launch")
        except Exception as e:
            logger.debug(f"Could not refresh spot daemon: {e}")

    def generate(
        self,
        categorized: Dict[str, str],
        entries: Dict[str, DesktopEntry],
        dry_run: bool = False,
        restart: bool = True,
    ) -> bool:
        usage_data = self.get_usage_data()
        category_list, by_category = group_and_sort(categorized, entries, usage_data)

        if dry_run:
            print(f"\n[DRY RUN] Would generate SpottyCat TOMLs in: {self.output_dir}")
            for cat in category_list:
                apps = by_category[cat]
                total_u = sum(int(usage_data.get(e.filename, {}).get("count", 0)) for e in apps)
                print(f"  - cat_{self._slug(cat)}.toml: {len(apps)} apps (usage: {total_u})")
            return True

        self.output_dir.mkdir(parents=True, exist_ok=True)
        index_apps: Dict[str, Dict] = {}
        apps_by_category_payload: Dict[str, List[Dict]] = {}
        cat_labels: List[str] = []
        grouped_rows: List[str] = []

        for cat in category_list:
            app_entries = by_category[cat]
            cat_labels.append(f"{cat}  ({len(app_entries)})")
            cat_items = []
            display_names = []

            for e in app_entries:
                record = {
                    "id": e.app_id,
                    "filename": e.filename,
                    "name": e.name,
                    "comment": e.comment,
                    "category": cat,
                    "exec": clean_exec(e.exec_cmd),
                    "terminal": e.terminal,
                }
                cat_items.append(record)
                index_apps[e.name] = record
                index_apps[e.app_id] = record
                display_names.append(e.name)
                grouped_rows.append(f"{cat}\t{e.name}")

            apps_by_category_payload[cat] = cat_items
            (self.output_dir / f"cat_{self._slug(cat)}.toml").write_text(
                self._build_cat_toml(cat, display_names), encoding="utf-8"
            )

        (self.output_dir / "categories.toml").write_text(
            self._build_categories_toml(cat_labels), encoding="utf-8"
        )
        (self.output_dir / "grouped.toml").write_text(
            self._build_grouped_toml(grouped_rows), encoding="utf-8"
        )
        (self.output_dir / "quick.toml").write_text(
            self._build_quick_toml(), encoding="utf-8"
        )
        (self.output_dir / "launcher.toml").write_text(
            self._build_launcher_toml(), encoding="utf-8"
        )
        self.index_path.write_text(
            json.dumps(
                {
                    "categoriesOrder": category_list,
                    "appsByCategory": apps_by_category_payload,
                    "appsByKey": index_apps,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        if restart:
            self.refresh_daemon()
        logger.info(f"Generated SpottyCat configs in {self.output_dir}")
        return True

    def cleanup(self, restart: bool = True) -> bool:
        try:
            if self.output_dir.exists():
                shutil.rmtree(self.output_dir)
            if restart:
                self.refresh_daemon()
            return True
        except Exception as e:
            logger.error(f"SpottyCat cleanup failed: {e}")
            return False

    # --- Runtime helpers invoked by Spot TOMLs ---------------------------------

    def _load_index(self) -> Dict:
        if not self.index_path.exists():
            return {}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def query_rows(self, query: str) -> List[str]:
        """Return tab-formatted source rows (`label\\tvalue\\tcomment`) for Spot [[sources]]."""
        data = self._load_index()
        q = query.strip().lower()
        rows: List[str] = []
        for cat in data.get("categoriesOrder", []):
            for app in data.get("appsByCategory", {}).get(cat, []):
                haystack = f"{cat} {app['name']} {app.get('comment', '')} {app['id']}".lower()
                if not q or all(term in haystack for term in q.split()):
                    comment = f"[{cat}] {app.get('comment', '')}".strip()
                    rows.append(f"{app['name']}\t{app['id']}\t{comment}")
        return rows

    def launch_selection(self, selection: str) -> int:
        """Launch an app selected from a Spot list or source by name or desktop id."""
        data = self._load_index()
        record = data.get("appsByKey", {}).get(selection.strip())
        if not record:
            logger.error(f"Unknown app selection: {selection}")
            return 1

        app_id = record["id"]
        if shutil.which("gtk-launch"):
            subprocess.Popen(
                ["gtk-launch", app_id],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return 0

        exec_cmd = record.get("exec", "")
        if not exec_cmd:
            return 1
        if record.get("terminal"):
            if shutil.which("xdg-terminal-exec"):
                cmd = f"xdg-terminal-exec {exec_cmd}"
            elif shutil.which("kitty"):
                cmd = f"kitty -e {exec_cmd}"
            else:
                cmd = exec_cmd
        elif os.environ.get("UWSM_FINALIZE_VARNAMES") and shutil.which("uwsm-app"):
            cmd = f"uwsm-app -- {exec_cmd}"
        else:
            cmd = exec_cmd

        subprocess.Popen(
            ["sh", "-c", cmd],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return 0

    def open_category(self, category_label: str) -> int:
        """Open a category dialog chained from categories.toml with SPOT_BACK."""
        category = category_label.split("  (", 1)[0].strip()
        toml_path = self.output_dir / f"cat_{self._slug(category)}.toml"
        if not toml_path.exists():
            logger.error(f"Category config not found: {toml_path}")
            return 1

        env = os.environ.copy()
        env["SPOT_BACK"] = f"spot {shlex.quote(str(self.output_dir / 'categories.toml'))}"
        subprocess.Popen(
            ["spot", "--chain", str(toml_path)],
            env=env,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return 0
