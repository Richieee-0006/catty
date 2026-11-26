"""Unit tests for Catty core, launcher backends, and dependency checks."""

import json
from pathlib import Path
from unittest.mock import patch

from catty.backends import get_backend
from catty.backends.base import clean_exec, group_and_sort
from catty.backends.spot import SpotBackend
from catty.backends.vicinae import VicinaeBackend
from catty.backends.walker import WalkerBackend
from catty.categorizer import AppCategorizer
from catty.main import main as cli_main
from catty.parser import DesktopEntry, DesktopFileParser
from catty.writer import DesktopFileWriter


def _make_entry(
    tmp_path: Path,
    filename: str,
    name: str,
    categories: str = "",
    exec_cmd: str = "app %U",
    comment: str = "",
) -> DesktopEntry:
    desktop = tmp_path / filename
    desktop.write_text(
        f"[Desktop Entry]\nType=Application\nName={name}\nExec={exec_cmd}\n"
        f"Comment={comment}\nCategories={categories}\n",
        encoding="utf-8",
    )
    entry = DesktopFileParser().parse_file(desktop)
    assert entry is not None
    return entry


def test_parser_and_game_fastpath(tmp_path: Path) -> None:
    steam = _make_entry(tmp_path, "cs2.desktop", "Counter-Strike 2", exec_cmd="steam steam://rungameid/730")
    hidden = tmp_path / "hidden.desktop"
    hidden.write_text("[Desktop Entry]\nType=Application\nName=Hidden\nNoDisplay=true\n", encoding="utf-8")

    entries = DesktopFileParser(search_dirs=[tmp_path]).scan_all()
    assert list(entries.keys()) == ["cs2.desktop"]
    assert steam.is_obvious_game() is True


def test_categorizer_parse_response_normalizes_categories() -> None:
    cat = AppCategorizer(auto_detect=False)
    raw = '<think>reasoning</think>\n```json\n{"a.desktop": "game", "b.desktop": "UnknownThing"}\n```'
    parsed = cat._parse_response(raw)
    assert parsed == {"a.desktop": "Games", "b.desktop": "Utility"}


def test_writer_applies_and_rolls_back(tmp_path: Path) -> None:
    sys_dir = tmp_path / "sys"
    user_dir = tmp_path / "user"
    bak_dir = tmp_path / "backups"
    sys_dir.mkdir()
    entry = _make_entry(sys_dir, "demo.desktop", "Demo App", exec_cmd="demo")

    writer = DesktopFileWriter(user_apps_dir=user_dir, backup_dir=bak_dir)
    res = writer.apply_categorization({"demo.desktop": entry}, {"demo.desktop": "Development"})
    assert res == {"demo.desktop": True}

    written = (user_dir / "demo.desktop").read_text(encoding="utf-8")
    assert "Categories=Development;" in written
    assert len(writer.list_backups()) == 1

    (user_dir / "demo.desktop").write_text("[Desktop Entry]\nName=Broken\n", encoding="utf-8")
    assert writer.rollback() is True
    assert "Name=Demo App" in (user_dir / "demo.desktop").read_text(encoding="utf-8")


def test_group_and_sort_dedups_and_orders_by_usage(tmp_path: Path) -> None:
    e1 = _make_entry(tmp_path, "firefox.desktop", "Firefox", categories="WebBrowser;")
    e2 = _make_entry(tmp_path, "firefox-dup.desktop", "Firefox", categories="WebBrowser;")
    e3 = _make_entry(tmp_path, "code.desktop", "VS Code", categories="Development;")

    entries = {"firefox.desktop": e1, "firefox-dup.desktop": e2, "code.desktop": e3}
    categorized = {
        "firefox.desktop": "Browser",
        "firefox-dup.desktop": "Browser",
        "code.desktop": "Development",
    }
    usage = {"code.desktop": {"count": 10}, "firefox.desktop": {"count": 2}}

    order, grouped = group_and_sort(categorized, entries, usage)
    assert order == ["Development", "Browser"]
    assert [e.filename for e in grouped["Browser"]] == ["firefox.desktop"]


def test_spot_backend_v07_outputs_and_frecency(tmp_path: Path) -> None:
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    e1 = _make_entry(apps_dir, "alpha.desktop", "Alpha", exec_cmd="alpha %F", comment="First")
    e2 = _make_entry(apps_dir, "beta.desktop", "Beta", exec_cmd="beta", comment="Second")

    frecency = tmp_path / "frecency.json"
    frecency.write_text(json.dumps({"beta": {"count": 5, "last": 1700000000}}), encoding="utf-8")

    out_dir = tmp_path / "spot_catty"
    (tmp_path / "spot.css").write_text(".spot-window { background: transparent; }\n", encoding="utf-8")
    backend = SpotBackend(output_dir=out_dir, frecency_path=frecency)
    assert backend.generate(
        {"alpha.desktop": "Utility", "beta.desktop": "Utility"},
        {"alpha.desktop": e1, "beta.desktop": e2},
        restart=False,
    )

    assert (out_dir / "categories.toml").exists()
    grouped_toml = (out_dir / "grouped.toml").read_text(encoding="utf-8")
    assert 'style = "../spot.css"' in grouped_toml
    quick_toml = (out_dir / "quick.toml").read_text(encoding="utf-8")
    assert "hide_empty = true" in quick_toml
    assert "default = true" in quick_toml
    assert "margin_top = 160" in quick_toml

    launcher_toml = (out_dir / "launcher.toml").read_text(encoding="utf-8")
    assert 'prefix = "#"' in launcher_toml
    assert 'show = "never"' in launcher_toml

    cat_toml = (out_dir / "cat_utility.toml").read_text(encoding="utf-8")
    assert 'options = ["Beta", "Alpha"]' in cat_toml

    rows = backend.query_rows("second")
    assert rows == ["Beta\tbeta\t[Utility] Second"]
    assert backend.cleanup(restart=False) is True
    assert not out_dir.exists()


def test_walker_backend_generates_menus_and_updates_config(tmp_path: Path) -> None:
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    e1 = _make_entry(apps_dir, "nvim.desktop", "Neovim", exec_cmd="nvim %F", comment="Editor")

    menus_dir = tmp_path / "menus"
    walker_cfg = tmp_path / "walker.toml"
    walker_cfg.write_text('[providers]\nempty = ["desktopapplications"]\n', encoding="utf-8")

    backend = WalkerBackend(menus_dir=menus_dir, walker_config=walker_cfg)
    assert backend.generate({"nvim.desktop": "Development"}, {"nvim.desktop": e1})
    assert (menus_dir / "catwalker_apps.toml").exists()
    assert (menus_dir / "apps_development.toml").exists()
    assert "menus:catwalker_apps" in walker_cfg.read_text(encoding="utf-8")
    assert backend.cleanup() is True
    assert not (menus_dir / "catwalker_apps.toml").exists()


def test_vicinae_backend_generates_extension_and_cleans_up(tmp_path: Path) -> None:
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    e1 = _make_entry(apps_dir, "kitty.desktop", "Kitty", exec_cmd="kitty")

    ext_dir = tmp_path / "ext"
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"favorites": ["existing:item"]}), encoding="utf-8")

    backend = VicinaeBackend(ext_dir=ext_dir, config_path=cfg, metadata_path=tmp_path / "meta.json")
    assert backend.generate({"kitty.desktop": "System"}, {"kitty.desktop": e1}, restart=False)
    assert (ext_dir / "package.json").exists()
    assert (ext_dir / "system.js").exists()

    updated_cfg = json.loads(cfg.read_text(encoding="utf-8"))
    assert "@vicicat/store.vicinae.vicicat:system" in updated_cfg["favorites"]

    assert backend.cleanup(restart=False) is True
    assert not ext_dir.exists()
    cleaned_cfg = json.loads(cfg.read_text(encoding="utf-8"))
    assert cleaned_cfg["favorites"] == ["existing:item"]


def test_backend_dependencies_and_cli_deps() -> None:
    with patch("shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name == "spot" else None):
        spot_req, spot_opt = SpotBackend().check_dependencies()
        assert spot_req == []
        assert len(spot_opt) >= 1

        walker_req, _ = WalkerBackend().check_dependencies()
        assert {d.binary for d in walker_req} == {"walker", "elephant"}

        assert cli_main(argv=["deps", "--target", "spot"]) == 0
        assert cli_main(argv=["deps", "--target", "walker"]) == 1
        assert cli_main(argv=["menus", "--target", "walker"]) == 1


def test_clean_exec_and_get_backend() -> None:
    assert clean_exec("code --reuse-window %F") == "code --reuse-window"
    assert get_backend("spot").name == "spot"
    assert get_backend("vicinae").name == "vicinae"
    assert get_backend("walker").name == "walker"
