# Hyprland Configuration Set

This repository is a TOML-first configuration source for Hyprland 0.55+ with
the CachyOS Hypr/Noctalia profile. `just` is the user-facing entry point. The
Python compiler is an internal implementation detail.

## Requirements

- Hyprland `>= 0.55.0` with Lua 5.5 configuration support
- Python `3.11+`
- `just`
- `lua5.5` for local Lua syntax checks when available
- A running Hyprland session for `just apply` and `just rollback`

The repository does not need to be the live Hyprland configuration root.

## First-time setup

Define the live configuration root once in the workstation environment:

```sh
export HYPRLAND_CONFIG_ROOT="$HOME/.config/hypr"
```

Link the hand-maintained entrypoints. `just install` refuses to overwrite
regular files or symlinks owned by another location:

```sh
just install
```

The command links `hyprland.lua` and `config/manual.lua`. Keep the repository
outside `HYPRLAND_CONFIG_ROOT`. Generated modules are written below
`$HYPRLAND_CONFIG_ROOT/config/generated/`.

The current application commands were mechanically migrated to
`config/variables.toml`. Edit them there. For a legacy file from another
checkout, `just migrate-variables` prints a candidate TOML and never changes
the old Lua file.

## Configuration sources

The hand-maintained sources are split by domain:

- `config/keymap.toml`: keybindings and the finite Adjust mode
- `config/variables.toml`: application command values
- `config/monitors.toml`: monitor rules
- `config/workspaces.toml`: workspace rules
- `config/input.toml`: global keyboard and mouse settings
- `config/rules.toml`: registered window and layer rules
- `config/environment.toml`: literal environment variables
- `config/autostart.toml`: allowlisted one-shot startup commands
- `config/manual.lua`: Hyprland APIs not covered by the schemas

Only `keymap.toml` and `variables.toml` currently contain formal configuration
values. Other domain files are optional and are not created with guessed
defaults. Missing files produce empty generated modules.

Generated Lua is never hand-edited and is ignored by Git:

```text
$HYPRLAND_CONFIG_ROOT/config/generated.lua
$HYPRLAND_CONFIG_ROOT/config/generated/*.lua
$HYPRLAND_CONFIG_ROOT/config/.generated-manifest.json
$HYPRLAND_CONFIG_ROOT/config/.generated-history.json
```

## Daily workflow

Edit the TOML source for the domain you want to change, then run:

```sh
just generate
just check
just test
just apply
```

`just generate` validates every source, generates all registered Lua modules,
updates the generated documentation, and writes the target manifest. It does
not reload Hyprland. `just check` performs the same validation without
modifying files and reports generated-file or documentation drift.

## Commands

| Command | Purpose |
| --- | --- |
| `just install` | Link the hand-maintained Hyprland entrypoints safely |
| `just generate` | Generate all deployed Lua modules and documentation |
| `just check` | Verify TOML, generated files, manifest, docs, entrypoint, and Lua syntax |
| `just list` | List domains, registered fields, the executable allowlist, and keymap usage |
| `just test` | Run the standard-library test suite |
| `just apply` | Precheck, snapshot, install, reload, validate, and automatically roll back on failure |
| `just rollback` | Restore the latest successfully applied generated configuration |
| `just migrate-variables` | Print a reviewed candidate migration from legacy `variables.lua` |

`just apply` refuses to start when the compositor already reports configuration
errors. It temporarily disables Hyprland autoreload, syntax-checks every
candidate, updates all generated files as one transaction, reloads, and checks
`hyprctl -j configerrors`. A failed reload restores the previous generated
file set and reloads it. Only one rollback layer is retained.

## Boundaries

The TOML compiler uses explicit, versioned schemas and rejects unknown fields.
It does not mirror all of Hyprland or Noctalia. Touchpad settings, device
overrides, gestures, permissions, plugins, complex shell logic, and Noctalia's
own configuration belong in `config/manual.lua` or their native configuration
systems. See [doc/CONFIG.md](doc/CONFIG.md) for the registered schema and
[doc/KEYMAP.md](doc/KEYMAP.md) for the keymap reference.
