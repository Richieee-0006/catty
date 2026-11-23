"""Launcher backend registry and target auto-detection."""

import shutil
import subprocess
from typing import Dict, List, Type

from .base import MenuBackend
from .spot import SpotBackend
from .vicinae import VicinaeBackend
from .walker import WalkerBackend

BACKEND_CLASSES: Dict[str, Type[MenuBackend]] = {
    "spot": SpotBackend,
    "vicinae": VicinaeBackend,
    "walker": WalkerBackend,
}


def _is_process_running(name: str) -> bool:
    try:
        res = subprocess.run(["pgrep", "-x", name], capture_output=True, check=False)
        return res.returncode == 0
    except Exception:
        return False


def get_backend(name: str) -> MenuBackend:
    if name not in BACKEND_CLASSES:
        raise ValueError(f"Unknown backend '{name}'. Choose from: {', '.join(BACKEND_CLASSES)}")
    return BACKEND_CLASSES[name]()


def resolve_targets(target: str) -> List[MenuBackend]:
    """Resolve CLI --target into one or more MenuBackend instances."""
    target = target.lower()
    if target == "all":
        return [cls() for cls in BACKEND_CLASSES.values()]
    if target != "auto":
        return [get_backend(target)]

    # Auto-detect running launcher first, then fall back to installed/configured ones
    for name in ("spot", "vicinae", "walker"):
        if _is_process_running(name) or (name == "spot" and shutil.which("spot")):
            backend = BACKEND_CLASSES[name]()
            if backend.is_available():
                return [backend]

    available = [cls() for cls in BACKEND_CLASSES.values() if cls().is_available()]
    if available:
        return [available[0]]

    # Default fallback to spot if nothing else detected yet
    return [SpotBackend()]
