"""Base interface and shared grouping/sorting helpers for launcher backends."""

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from ..config import DEFAULT_CATEGORIES
from ..parser import DesktopEntry


@dataclass(frozen=True)
class ToolDep:
    """External launcher or helper tool required/optional for a backend."""

    binary: str
    package: str
    url: str
    required: bool = True
    purpose: str = ""

    def is_installed(self) -> bool:
        return bool(shutil.which(self.binary))

SKIP_DESKTOP_CATEGORIES = {"X-LSP-Plugins"}
SKIP_APP_NAMES = {
    "Steamworks SDK Redist",
    "Steamworks Common Redistributables",
    "Proton",
}
_FIELD_CODES = ("%u", "%U", "%f", "%F", "%d", "%D", "%n", "%N", "%i", "%c", "%k", "%v", "%m")


def clean_exec(exec_cmd: str) -> str:
    """Strip freedesktop field codes from an Exec= string."""
    for code in _FIELD_CODES:
        exec_cmd = exec_cmd.replace(code, "")
    return exec_cmd.strip()


def group_and_sort(
    categorized: Dict[str, str],
    entries: Dict[str, DesktopEntry],
    usage_data: Dict[str, Dict],
    disabled_app_ids: Optional[Set[str]] = None,
) -> Tuple[List[str], Dict[str, List[DesktopEntry]]]:
    """Filter, deduplicate, and sort categorized entries and category order by usage."""
    disabled = disabled_app_ids or set()
    by_category: Dict[str, List[DesktopEntry]] = {}

    for filename, category in categorized.items():
        entry = entries.get(filename)
        if not entry or entry.app_id in disabled:
            continue
        if any(c in SKIP_DESKTOP_CATEGORIES for c in entry.categories):
            continue
        if any(skip.lower() in entry.name.lower() for skip in SKIP_APP_NAMES):
            continue
        by_category.setdefault(category, []).append(entry)

    def usage_count(filename: str) -> int:
        return int(usage_data.get(filename, {}).get("count", 0))

    for cat in by_category:
        by_category[cat].sort(key=lambda e: (-usage_count(e.filename), e.name.lower()))
        seen_names = set()
        deduped = []
        for entry in by_category[cat]:
            norm = entry.name.strip().lower()
            if norm not in seen_names:
                seen_names.add(norm)
                deduped.append(entry)
        by_category[cat] = deduped

    category_list = list(by_category.keys())
    category_list.sort(
        key=lambda c: (
            -sum(usage_count(e.filename) for e in by_category[c]),
            DEFAULT_CATEGORIES.index(c) if c in DEFAULT_CATEGORIES else len(DEFAULT_CATEGORIES),
        )
    )
    return category_list, by_category


class MenuBackend(ABC):
    """Abstract launcher menu generator backend."""

    name: str = ""
    dependencies: Tuple[ToolDep, ...] = ()

    def check_dependencies(self) -> Tuple[List[ToolDep], List[ToolDep]]:
        """Return (missing_required, missing_optional) external tool dependencies."""
        missing_req = [d for d in self.dependencies if d.required and not d.is_installed()]
        missing_opt = [d for d in self.dependencies if not d.required and not d.is_installed()]
        return missing_req, missing_opt

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this launcher appears installed/configured on the system."""

    @abstractmethod
    def output_exists(self) -> bool:
        """Return True if generated menu artifacts currently exist."""

    @abstractmethod
    def get_usage_data(self) -> Dict[str, Dict]:
        """Return {filename: {'count': int, 'last_used': Any}} usage stats."""

    @abstractmethod
    def generate(
        self,
        categorized: Dict[str, str],
        entries: Dict[str, DesktopEntry],
        dry_run: bool = False,
        restart: bool = True,
    ) -> bool:
        """Generate launcher menus/extension for categorized apps."""

    @abstractmethod
    def cleanup(self, restart: bool = True) -> bool:
        """Remove generated launcher menus/extension."""
