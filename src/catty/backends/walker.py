"""Walker / Elephant launcher backend: TOML category menus & gob usage history."""

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

from ..config import WALKER_CONFIG_PATH, WALKER_MENUS_DIR
from ..parser import DesktopEntry
from .base import MenuBackend, clean_exec, group_and_sort

logger = logging.getLogger(__name__)

CATEGORY_ICONS = {
    "Development": "applications-development",
    "System": "applications-system",
    "Media": "applications-multimedia",
    "Office": "applications-office",
    "Games": "applications-games",
    "Internet": "applications-internet",
    "Graphics": "applications-graphics",
    "Utility": "applications-utilities",
    "Settings": "preferences-system",
    "Education": "applications-science",
    "Browser": "applications-internet",
}

MAIN_MENU_NAME = "catwalker_apps"


class WalkerBackend(MenuBackend):
    """Generates Elephant TOML menu files and updates Walker config."""

    name = "walker"

    def __init__(
        self,
        menus_dir: Path = WALKER_MENUS_DIR,
        walker_config: Path = WALKER_CONFIG_PATH,
    ):
        self.menus_dir = menus_dir
        self.walker_config = walker_config

    def is_available(self) -> bool:
        return bool(shutil.which("walker")) or self.walker_config.exists() or self.menus_dir.exists()

    def output_exists(self) -> bool:
        return (self.menus_dir / f"{MAIN_MENU_NAME}.toml").exists()

    def _sanitize_name(self, name: str) -> str:
        return "apps_" + name.lower().replace(" ", "_")

    def _escape_toml(self, text: str) -> str:
        return (
            text.replace('"', '\\"').replace("\n", " ").encode("ascii", errors="replace").decode("ascii")
        )

    def get_usage_data(self) -> Dict[str, Dict]:
        usage: Dict[str, Dict] = {}
        gob_src = Path(__file__).with_name("gob_reader.go")
        gob_bin = Path(__file__).with_name("gob_reader")

        if not gob_bin.exists():
            if not gob_src.exists() or not shutil.which("go"):
                return usage
            try:
                subprocess.run(["go", "build", "-o", str(gob_bin), str(gob_src)], check=True)
            except Exception as e:
                logger.warning(f"Could not build gob_reader: {e}")
                return usage

        try:
            result = subprocess.run([str(gob_bin)], capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            for term_data in data.values():
                for app_filename, stats in term_data.items():
                    amount = stats.get("Amount", 0)
                    last_used = stats.get("LastUsed", "")
                    if app_filename not in usage:
                        usage[app_filename] = {"count": 0, "last_used": last_used}
                    usage[app_filename]["count"] += amount
                    if last_used and (
                        not usage[app_filename]["last_used"]
                        or last_used > usage[app_filename]["last_used"]
                    ):
                        usage[app_filename]["last_used"] = last_used
        except Exception as e:
            logger.debug(f"Could not load Walker usage data: {e}")
        return usage

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
            print(f"\n[DRY RUN] Would generate Walker/Elephant menus in: {self.menus_dir}")
            print(f"  {self.menus_dir}/{MAIN_MENU_NAME}.toml (main categories menu)")
            for cat in category_list:
                apps = by_category[cat]
                usage_sum = sum(int(usage_data.get(e.filename, {}).get("count", 0)) for e in apps)
                print(f"  {self.menus_dir}/{self._sanitize_name(cat)}.toml ({len(apps)} apps, usage: {usage_sum})")
            return True

        try:
            self.menus_dir.mkdir(parents=True, exist_ok=True)
            self._write_main_menu(category_list)
            for cat in category_list:
                self._write_category_menu(cat, by_category[cat])
            self.update_walker_config()
            logger.info(f"Generated {len(category_list) + 1} Walker menu files in {self.menus_dir}")
            return True
        except Exception as e:
            logger.error(f"Failed during Walker menu generation: {e}")
            return False

    def _update_section_content(self, section_content: str, provider_name: str) -> str:
        empty_match = re.search(r"^empty\s*=\s*\[(.*?)\]", section_content, re.MULTILINE)
        if empty_match:
            items_str = empty_match.group(1).strip()
            items = [i.strip().strip('"').strip("'") for i in items_str.split(",") if i.strip()]
            if provider_name not in items:
                items.append(provider_name)
                new_items_str = ", ".join(f'"{i}"' for i in items)
                return section_content.replace(empty_match.group(0), f"empty = [{new_items_str}]")
            return section_content
        return section_content.rstrip() + f'\nempty = ["{provider_name}"]\n'

    def update_walker_config(self) -> bool:
        if not self.walker_config.exists():
            logger.warning(f"Walker config not found at {self.walker_config}")
            return False

        provider_name = f"menus:{MAIN_MENU_NAME}"
        try:
            content = self.walker_config.read_text(encoding="utf-8")
            new_content = content
            provider_match = re.search(r"^\[providers\]", new_content, re.MULTILINE)

            if provider_match:
                next_section = re.search(r"^\[", new_content[provider_match.end() :], re.MULTILINE)
                section_end = (
                    (provider_match.end() + next_section.start()) if next_section else len(new_content)
                )
                section_content = new_content[provider_match.start() : section_end]
                updated_section = self._update_section_content(section_content, provider_name)
                new_content = (
                    new_content[: provider_match.start()] + updated_section + new_content[section_end:]
                )
            else:
                if not new_content.endswith("\n"):
                    new_content += "\n"
                new_content += f'\n[providers]\nempty = ["{provider_name}"]\n'

            if new_content != content and "[providers]" in new_content and provider_name in new_content:
                self.walker_config.write_text(new_content, encoding="utf-8")
                logger.info(f"Updated Walker config: {self.walker_config}")
            return True
        except Exception as e:
            logger.error(f"Failed to update Walker config at {self.walker_config}: {e}")
            return False

    def _write_main_menu(self, categories: List[str]) -> None:
        lines = [
            f'name = "{MAIN_MENU_NAME}"',
            'name_pretty = "Apps"',
            'icon = "applications-other"',
            "search_name = true",
            "history = true",
            "",
        ]
        for category in categories:
            menu_name = self._sanitize_name(category)
            icon = CATEGORY_ICONS.get(category, "applications-other")
            lines += [
                "[[entries]]",
                f'text = "{category}"',
                f'icon = "{icon}"',
                f'submenu = "{menu_name}"',
                "",
            ]
        (self.menus_dir / f"{MAIN_MENU_NAME}.toml").write_text("\n".join(lines), encoding="utf-8")

    def _write_category_menu(self, category: str, app_entries: List[DesktopEntry]) -> None:
        menu_name = self._sanitize_name(category)
        icon = CATEGORY_ICONS.get(category, "applications-other")
        lines = [
            f'name = "{menu_name}"',
            f'name_pretty = "{category}"',
            f'icon = "{icon}"',
            f'parent = "{MAIN_MENU_NAME}"',
            "search_name = true",
            "history = true",
            "",
        ]
        for entry in app_entries:
            exec_cmd = clean_exec(entry.exec_cmd)
            if not exec_cmd:
                continue
            name = self._escape_toml(entry.name)
            icon_name = self._escape_toml(entry.icon) if entry.icon else "application-x-executable"
            lines += ["[[entries]]", f'text = "{name}"']
            if entry.comment:
                lines.append(f'subtext = "{self._escape_toml(entry.comment)}"')
            if entry.generic_name:
                lines.append(f'keywords = ["{self._escape_toml(entry.generic_name)}"]')
            lines += [
                f'icon = "{icon_name}"',
                f'actions = {{ launch = "{self._escape_toml(exec_cmd)}" }}',
                "",
            ]
        (self.menus_dir / f"{menu_name}.toml").write_text("\n".join(lines), encoding="utf-8")

    def cleanup(self, restart: bool = True) -> bool:
        try:
            if not self.menus_dir.exists():
                return True
            for pattern in ("catwalker_*.toml", "apps_*.toml"):
                for f in self.menus_dir.glob(pattern):
                    f.unlink()
            return True
        except Exception as e:
            logger.error(f"Walker cleanup failed: {e}")
            return False
