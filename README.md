# Catty

Unified Linux application & game categorizer for **Spot** (`spottycat`), **Vicinae** (`vicicat`), and **Walker / Elephant** (`catwalker`).

Combines [CatWalker](https://github.com/Richieee-0006/CatWalker) and [ViciCat](https://github.com/Richieee-0006/ViciCat) into one shared categorization core with pluggable launcher backends.

## Supported Launchers & Dependencies

Install at least one target launcher before running `catty menus`:

| Backend (`--target`) | Required Tool(s) | Arch / AUR Package(s) | Optional Helpers | Upstream |
|---|---|---|---|---|
| `spot` (`spottycat`) | `spot` (`>= 0.7.0`) | `spot-bin` (or `spot-git`) | `libqalculate` (`qalc`), `fd`, `wl-clipboard`, `glib2` (`gtk-launch`) | [KopyTKG/spot](https://github.com/KopyTKG/spot) |
| `vicinae` (`vicicat`) | `vicinae` | `vicinae-bin` | `systemd` | [vicinaehq/vicinae](https://github.com/vicinaehq/vicinae) |
| `walker` (`catwalker`) | `walker`, `elephant` | `walker-bin`, `elephant-bin` | `go` (builds `gob_reader.go` for history) | [abenz1267/walker](https://github.com/abenz1267/walker), [abenz1267/elephant](https://github.com/abenz1267/elephant) |

Verify installed launcher dependencies at any time:

```bash
catty deps --target all
catty deps --target spot
```

An Arch Linux package manifest declaring these `optdepends` is included in [`packaging/arch/PKGBUILD`](packaging/arch/PKGBUILD).

## Features

- **Shared LLM Categorizer**: Local-first via [Ollama](https://ollama.com) or OpenAI-compatible servers (`llama-swap` on `:8080`), with Google Gemini/Gemma REST fallback (`GEMINI_API_KEY`).
- **Zero-Token Game Fast-Path**: Instantly classifies Steam (`steam://rungameid/`), Lutris (`lutris:rungame`), Heroic (`heroic://launch`), and Prism Launcher entries into `Games`.
- **Safe `.desktop` Writes**: Updates only `~/.local/share/applications/` with timestamped backups and `catty rollback`.
- **Dependency Preflight**: `catty menus` checks required binaries for the selected backend and prints package/URL hints if missing (override with `--ignore-deps`).
- **Three Launcher Backends**:
  - **Spot (`--target spot`, `>= 0.7.0`)**: Generates `~/.config/spot/catty/` (`categories.toml`, `cat_<slug>.toml`, `grouped.toml` collapsible tree, `quick.toml` v0.7 run-bar search with `default = true` + `hide_empty = true`, `launcher.toml` with `#` category prefix) and reads `$XDG_STATE_HOME/spot/frecency.json`.
  - **Vicinae (`--target vicinae`)**: Generates native `@vicinae/api` extension in `~/.local/share/vicinae/extensions/store.vicinae.vicicat`, pins favorites, and reads `metadata.json` visit counts.
  - **Walker (`--target walker`)**: Generates Elephant TOML menus in `~/.config/elephant/menus/`, updates `~/.config/walker/config.toml`, and reads Elephant `.gob` history via `gob_reader.go`.
- **Systemd Automation**: `catty service install` sets up `catty-watcher.path` and `catty-sync.timer`.

## Quick Start

```bash
git clone https://github.com/Richieee-0006/catty.git ~/Projects/catty
cd ~/Projects/catty

python3 -m venv .venv
source .venv/bin/activate
pip install -e .

ln -sf "$(pwd)/catty" ~/.local/bin/catty
# Optional per-launcher aliases:
ln -sf "$(pwd)/catty" ~/.local/bin/spottycat
ln -sf "$(pwd)/catty" ~/.local/bin/vicicat
ln -sf "$(pwd)/catty" ~/.local/bin/catwalker
```

## Usage

```bash
# Check required & optional launcher binaries
catty deps --target all

# Scan & categorize uncategorized apps
catty scan --uncategorized
catty categorize --yes

# Generate menus (auto-detects running launcher, or specify target)
catty menus --target spot
catty menus --target vicinae
catty menus --target walker
catty menus --target all

# Non-interactive sync + systemd watcher
catty auto --target spot --force
catty service install --target spot
```

### Using SpottyCat with `spot` (`>= 0.7.0`)

```bash
spot ~/.config/spot/catty/categories.toml   # category picker -> chained app list with Back
spot ~/.config/spot/catty/grouped.toml      # collapsible category tree
spot ~/.config/spot/catty/quick.toml        # v0.7 run-bar instant search (hide_empty + default source)
spot ~/.config/spot/catty/launcher.toml     # full app launcher with #, =, ., > prefixes
```

## License

MIT — richieee @ 2026
