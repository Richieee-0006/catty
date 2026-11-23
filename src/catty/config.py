"""Configuration, paths, and category mappings for Catty."""

import os
from pathlib import Path


def _env(key: str, legacy_key: str, default: str) -> str:
    return os.getenv(key) or os.getenv(legacy_key) or default


# Target launcher backend (auto | walker | vicinae | spot | all)
DEFAULT_TARGET = os.getenv("CATTY_TARGET", os.getenv("CATTY_DEFAULT_TARGET", "auto"))

# LLM Configuration (Local-first with Cloud fallback)
PROVIDER = _env("CATTY_PROVIDER", "VICICAT_PROVIDER", "auto")

# Local LLM (Ollama or OpenAI-compatible like llama-swap)
LOCAL_API_URL = _env("CATTY_LOCAL_URL", "VICICAT_LOCAL_URL", "http://127.0.0.1:11434")
LOCAL_MODEL = _env("CATTY_LOCAL_MODEL", "VICICAT_LOCAL_MODEL", "gemma4:26b-a4b-it-qat")

# Cloud LLM (Google Gemini / Gemma REST API)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
CLOUD_MODEL = _env("CATTY_CLOUD_MODEL", "VICICAT_CLOUD_MODEL", "gemma-3-27b-it")

MAX_RETRIES = 3
TIMEOUT = 120

# XDG Base Directories
XDG_DATA_HOME = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local/share"))
XDG_CONFIG_HOME = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
XDG_STATE_HOME = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local/state"))
XDG_CACHE_HOME = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache"))

# Desktop entry directories
SYSTEM_APPS_DIR = Path("/usr/share/applications")
USER_APPS_DIR = XDG_DATA_HOME / "applications"
FLATPAK_SYSTEM_APPS_DIR = Path("/var/lib/flatpak/exports/share/applications")
FLATPAK_USER_APPS_DIR = XDG_DATA_HOME / "flatpak/exports/share/applications"

# Catty state & backups
APP_DATA_DIR = XDG_DATA_HOME / "catty"
BACKUP_DIR = APP_DATA_DIR / "backups"
STATE_FILE = APP_DATA_DIR / "state.json"

# Walker / Elephant paths
WALKER_CONFIG_PATH = XDG_CONFIG_HOME / "walker/config.toml"
WALKER_MENUS_DIR = XDG_CONFIG_HOME / "elephant/menus"

# Vicinae paths
VICINAE_CONFIG_PATH = XDG_CONFIG_HOME / "vicinae/settings.json"
VICINAE_DATA_DIR = XDG_DATA_HOME / "vicinae"
VICINAE_METADATA_PATH = VICINAE_DATA_DIR / "metadata.json"
VICINAE_EXT_ID = "store.vicinae.vicicat"
VICINAE_EXT_AUTHOR = "vicicat"
VICINAE_EXT_DIR = VICINAE_DATA_DIR / "extensions" / VICINAE_EXT_ID

# Spot paths
SPOT_CONFIG_DIR = XDG_CONFIG_HOME / "spot"
SPOT_CATTY_DIR = SPOT_CONFIG_DIR / "catty"
SPOT_FRECENCY_PATH = XDG_STATE_HOME / "spot/frecency.json"

DEFAULT_CATEGORIES = [
    "Games",
    "Development",
    "Browser",
    "Internet",
    "Media",
    "Graphics",
    "Office",
    "Education",
    "Utility",
    "System",
    "Settings",
]

CATEGORY_MAPPINGS = {
    "Development": "Development",
    "System": "System",
    "Media": "AudioVideo",
    "Office": "Office",
    "Games": "Game",
    "Browser": "WebBrowser",
    "Internet": "Network",
    "Graphics": "Graphics",
    "Utility": "Utility",
    "Settings": "Settings",
    "Education": "Education",
}

REVERSE_CATEGORY_MAPPING = {
    "WebBrowser": "Browser",
    "Development": "Development",
    "System": "System",
    "AudioVideo": "Media",
    "Audio": "Media",
    "Video": "Media",
    "Office": "Office",
    "Game": "Games",
    "Network": "Internet",
    "Graphics": "Graphics",
    "Utility": "Utility",
    "Settings": "Settings",
    "Education": "Education",
}

CATEGORIZATION_PROMPT = """You are an expert at categorizing Linux desktop applications.

Categorize each application into ONE of these categories:
{categories}

Rules:
- Choose the MOST appropriate single category
- Steam, Lutris, Heroic, Prism Launcher, Minecraft, and video games MUST be categorized as "Games"
- If unsure, use "Utility"
- Return ONLY valid JSON format with no markdown explanation

Format:
{{
  "app_filename.desktop": "Category"
}}

Applications:
{applications}"""
