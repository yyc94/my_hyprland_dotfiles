# Hyprland Configuration Set

TOML-driven keybindings for Hyprland 0.55+ on the CachyOS Hypr/Noctalia profile.
The hand-maintained keybinding source is `config/keymap.toml`. Lua and the keymap
documentation are generated from it.

## Requirements

- Hyprland `>= 0.55.0` with its Lua 5.5 configuration support
- Python `3.11+`
- `just`
- A running Hyprland session for `apply` and `rollback`
- Noctalia and the commands used by the selected bindings on the target system

The repository is the source tree. It does not have to be the live Hyprland
configuration root.

## First-time setup

Define the live configuration root once in the workstation environment:

```sh
export HYPRLAND_CONFIG_ROOT="$HOME/.config/hypr"
```

Make the native entrypoint and application variables available from that root.
For an existing Hyprland configuration, symlinks avoid copying these files:

```sh
mkdir -p "$HYPRLAND_CONFIG_ROOT/config"
ln -sfn "$PWD/hyprland.lua" "$HYPRLAND_CONFIG_ROOT/hyprland.lua"
ln -sfn "$PWD/config/variables.lua" "$HYPRLAND_CONFIG_ROOT/config/variables.lua"
```

The entrypoint loads `config.variables` first and the generated `config.binds`
second. Keep the repository outside `HYPRLAND_CONFIG_ROOT`; `just generate`
refuses to overwrite the repository when it is also the live root.

## Daily workflow

Edit `config/keymap.toml`, then run:

```sh
just generate
just check
just test
just apply
```

`just generate` writes:

- `$HYPRLAND_CONFIG_ROOT/config/binds.lua`
- `doc/KEYMAP.md`

The generated Lua is not hand-edited. `just check` detects TOML, generated-file,
entrypoint, and optional Lua syntax drift. Hyprland reload and
`hyprctl -j configerrors` are authoritative on the target workstation.

## Commands

| Command | Purpose |
| --- | --- |
| `just generate` | Validate and generate the deployed Lua and keymap document |
| `just check` | Verify generated files and Lua entrypoint synchronization |
| `just list` | Show supported actions and occupied chords |
| `just test` | Run the Python test suite |
| `just apply` | Syntax-check, save one rollback layer, install, reload, and validate |
| `just rollback` | Restore the latest applied `binds.lua` without changing TOML |

`just apply` requires the current compositor configuration to have no existing
errors. If the candidate reload fails, the previous `binds.lua` is restored and
reloaded automatically. Only one rollback layer is retained.

## Keymap reference

See [doc/KEYMAP.md](doc/KEYMAP.md) for the complete generated action list,
current bindings, chord syntax, special keys, mouse bindings, and XF86 keys.

The default scheme has Normal and one finite Adjust mode. `SUPER+A` enters
Adjust; `Esc` or `Enter` exits it. Hardware and recovery bindings remain
available in Adjust mode, and hardware controls remain available while the
session is locked.
