<!-- GENERATED FILE. DO NOT EDIT. -->
<!-- Sources: config/*.toml and the schema registry -->
<!-- Content-SHA256: 593e229c60bc880a23e1394f672a90cd957d19a2ecf28a0d748382ede7d069ae -->

# TOML Configuration

This document is generated from the compiler's registered TOML schemas and describes every field accepted by the compiler. Generated Lua is deployed under `$HYPRLAND_CONFIG_ROOT/config/generated/`.
Unknown fields are rejected. Unlisted fields are intentionally unsupported and belong in `config/manual.lua` or the native configuration of the relevant component.

## How to use

Every domain file below starts with the same required metadata table. Each source is optional as a file; a missing file produces an empty module and never adds hidden defaults. The keymap has its own schema documented in [KEYMAP.md](KEYMAP.md).

```toml
[meta]
schema = "1"
target_hyprland = ">=0.55.0"
profile = "CachyOS Hypr/Noctalia"
```

`schema` accepts the integer `1` or string `"1"`; `target_hyprland` must exactly be `">=0.55.0"`; `profile` must be a non-empty string. The compiler does not infer values from Hyprland defaults. Omit a field to leave that setting untouched.

## Domains

| Source | TOML tables | Generated API |
| --- | --- | --- |
| `variables.toml` | `[commands]` | returns command data for keymap |
| `monitors.toml` | `[[monitor]]` | `hl.monitor` |
| `workspaces.toml` | `[[workspace]]` | `hl.workspace_rule` |
| `input.toml` | `[keyboard]`, `[mouse]` | `hl.config({ input = ... })` |
| `rules.toml` | `[[windowrule]]`, `[[layerrule]]` | `hl.window_rule`, `hl.layer_rule` |
| `environment.toml` | `[environment]` | `hl.env` |
| `autostart.toml` | `[[exec_once]]` | `hl.on("hyprland.start")` and `hl.exec_cmd` |

## variables.toml

```toml
[commands]
terminal = "kitty"
file_manager = "yazi"
browser = "zen-browser"
calculator = "gnome-calculator"
system_monitor = "btop"
```

`[commands]` is a table. Every key must match `[A-Za-z_][A-Za-z0-9_]*` so it can be used as a Lua identifier, and every value must be a non-empty string. The current keymap's five application actions require these exact command keys: `terminal`, `file_manager`, `browser`, `calculator`, and `system_monitor`. Additional identifier-shaped command keys are allowed for future generated consumers.

## monitors.toml

```toml
[[monitor]]
output = "DP-1"
mode = "preferred"
position = { x = 0, y = 0 }
scale = 1.0
disabled = false
transform = "normal"
vrr = "off"
```

Each `[[monitor]]` entry must have a unique non-empty `output` string. The accepted fields are:

| Field | Type and validation |
| --- | --- |
| `output` | required non-empty string; unique within the file |
| `mode` | optional non-empty string such as `preferred` or `1920x1080@60` |
| `position` | optional `"auto"` or a table with exactly integer `x` and `y`; compiled as a Hyprland position string such as `"0x0"` |
| `scale` | optional `"auto"` or finite number >= `0.25` |
| `disabled` | optional boolean |
| `transform` | optional string `normal`, `90`, `180`, `270`, `flipped`, `flipped-90`, `flipped-180`, or `flipped-270`; integer `90`, `180`, or `270` is also accepted |
| `vrr` | optional `off`, `on`, or `fullscreen` |

`transform` and `vrr` are translated to the integer values expected by Hyprland. Monitor syntax and monitor existence are finally checked by Hyprland during reload.

## workspaces.toml

```toml
[[workspace]]
workspace = "1"
monitor = "DP-1"
default = true
persistent = true
layout = "master"
```

Each `[[workspace]]` entry must have a unique non-empty `workspace` selector string. The accepted fields are:

| Field | Type and validation |
| --- | --- |
| `workspace` | required non-empty string selector; unique within the file |
| `monitor` | optional non-empty monitor selector string |
| `default` | optional boolean |
| `persistent` | optional boolean |
| `layout` | optional non-empty layout name string |

Workspace selectors are passed to `hl.workspace_rule` literally. The compiler does not assign workspaces to monitors unless `monitor` is explicitly present.

## input.toml

```toml
[keyboard]
layout = "us"
variant = ""
model = ""
options = ""
rules = ""
repeat_rate = 25
repeat_delay = 600
numlock_by_default = false
resolve_binds_by_sym = false

[mouse]
follow = "follow"
sensitivity = 0.0
accel_profile = "adaptive"
scroll_method = "2fg"
```

Both `[keyboard]` and `[mouse]` are optional tables. Omitted tables and fields are not filled with compiler defaults. All settings are emitted through `hl.config({ input = ... })`.

### Keyboard fields

| Field | Type and validation |
| --- | --- |
| `layout`, `variant`, `model`, `options`, `rules` | optional string; empty string is allowed |
| `repeat_rate` | optional integer from `0` to `200` |
| `repeat_delay` | optional integer from `0` to `2000` |
| `numlock_by_default` | optional boolean |
| `resolve_binds_by_sym` | optional boolean |

### Mouse fields

| Field | Type and validation |
| --- | --- |
| `follow` | `disabled`, `follow`, `detached`, or `separate` |
| `follow_threshold` | finite number >= `0` |
| `focus_on_close` | `next`, `cursor`, or `mru` |
| `mouse_refocus` | boolean |
| `float_switch_override_focus` | integer from `0` to `2` |
| `sensitivity` | finite number from `-1` to `1` |
| `accel_profile` | `adaptive`, `flat`, or `custom` |
| `force_no_accel` | boolean |
| `rotation` | integer from `0` to `359` |
| `left_handed` | boolean |
| `scroll_method` | `2fg`, `edge`, `on_button_down`, or `no_scroll` |
| `scroll_button` | integer from `0` to `300` |
| `scroll_button_lock` | boolean |
| `scroll_points` | string; empty string is allowed |
| `scroll_factor` | finite number from `0` to `2` |
| `natural_scroll` | boolean |
| `special_fallthrough` | boolean |
| `off_window_axis_events` | `ignore`, `send`, `clamp`, or `warp` |
| `emulate_discrete_scroll` | `disable`, `non_standard`, or `force_all` |
| `follow_mouse_shrink` | integer from `0` to `300` |

`follow`, `focus_on_close`, `off_window_axis_events`, and `emulate_discrete_scroll` are translated to the integer values used by Hyprland. `accel_profile` and `scroll_method` remain strings. Touchpad and device-specific settings are deliberately outside this schema; see [Escape hatch](#escape-hatch).

## rules.toml

Rules use arrays of tables and separate `match` and `effects` subtables:

```toml
[[windowrule]]
name = "floating-calculator"
enabled = true

[windowrule.match]
class = "org.example.Calculator"

[windowrule.effects]
float = true
center = true
size = { x = 800, y = 600 }
```

The same shape is used for `[[layerrule]]`. `name` is required and unique within its rule kind; `enabled` is optional and defaults to `true`; `match` and `effects` are both required and must each contain at least one field. The compiler flattens validated effects into the table passed to Hyprland. Matcher strings are passed to Hyprland's regex/workspace/tag engines; regex semantics are not checked by the compiler.

### Rule entry fields

| Field | Type and validation |
| --- | --- |
| `name` | required non-empty string; unique within `windowrule` or `layerrule` |
| `enabled` | optional boolean; defaults to `true` |
| `match` | required non-empty table using the matcher fields below |
| `effects` | required non-empty table using the effect fields below |

### Match fields

| Rule kind | Fields | Type and validation |
| --- | --- | --- |
| `windowrule` | `class`, `content`, `initial_class`, `initial_title`, `namespace`, `tag`, `title`, `workspace`, `xdg_tag` | non-empty string |
| `windowrule` | `float`, `focus`, `fullscreen`, `group`, `modal`, `pin`, `xwayland` | boolean |
| `windowrule` | `fullscreen_state_client`, `fullscreen_state_internal` | integer |
| `layerrule` | `namespace` | non-empty string |

### Window effects

| Type | Fields | Validation |
| --- | --- | --- |
| boolean | `allows_input`, `center`, `confine_pointer`, `decorate`, `dim_around`, `float`, `focus_on_activate`, `force_rgbx`, `fullscreen`, `immediate`, `keep_aspect_ratio`, `maximize`, `nearest_neighbor`, `no_anim`, `no_blur`, `no_dim`, `no_focus`, `no_follow_mouse`, `no_initial_focus`, `no_max_size`, `no_screen_share`, `no_shadow`, `no_shortcuts_inhibit`, `no_vrr`, `opaque`, `persistent_size`, `pin`, `pseudo`, `render_unfocused`, `stay_focused`, `sync_fullscreen`, `tile`, `xray` | boolean |
| string | `animation`, `content`, `fullscreen_state`, `group`, `idle_inhibit`, `monitor`, `opacity`, `suppress_event`, `tag`, `workspace` | non-empty string |
| integer | `border_size`, `no_close_for`, `rounding` | `rounding` and `border_size` >= `0`; `rounding` <= `20`; `no_close_for` has no compiler range |
| number | `rounding_power`, `scroll_mouse`, `scroll_touchpad`, `scrolling_width` | finite number; `scroll_mouse` and `scroll_touchpad` are `0.01` to `10` |
| vec2 table | `max_size`, `min_size`, `move`, `size` | table with exactly numeric `x` and `y`; compiled as a two-element Lua array |

### Layer effects

| Type | Fields | Validation |
| --- | --- | --- |
| boolean | `blur`, `blur_popups`, `dim_around`, `no_anim`, `no_screen_share`, `xray` | boolean |
| string | `animation` | non-empty string |
| integer | `above_lock`, `order` | `above_lock` is `0` to `2`; `order` has no compiler range |
| number | `ignore_alpha` | `ignore_alpha` is `0` to `1` |

The compiler validates the type and ranges shown above. Hyprland may perform additional semantic validation during reload.

## environment.toml

```toml
[environment]
XCURSOR_SIZE = "24"
HYPRCURSOR_SIZE = "24"
```

`[environment]` is a table. Names must match `[A-Za-z_][A-Za-z0-9_]*`; values must be non-empty strings. Values are literal: there is no shell expansion, command substitution, or implicit import from the current shell. Each entry is emitted as `hl.env(name, value)`.

## autostart.toml

```toml
[[exec_once]]
name = "status-bar"
command = ["waybar", "--bar"]
```

Each `[[exec_once]]` entry has a unique name matching `[A-Za-z_][A-Za-z0-9_-]*` and a non-empty `command` array. Every array element must be a non-empty string. The first element must be a bare executable name from this allowlist:

`brightnessctl`, `grim`, `hypridle`, `hyprlock`, `hyprpaper`, `hyprpicker`, `noctalia`, `noctalia-shell`, `notify-send`, `pamixer`, `playerctl`, `slurp`, `systemctl`, `true`, `waybar`, `wl-copy`.

Absolute or relative executable paths are rejected. Shell operators, command substitution, and backtick substitution are rejected; use `config/manual.lua` for shell logic outside this restricted form. Commands are emitted as a shell-quoted string to `hl.exec_cmd` inside the `hyprland.start` event.

## Generated files and validation

`just generate` writes the generated modules and this documentation to the configured target/repository locations. `just check` performs the same build without modifying anything and detects generated-file, manifest, documentation, entrypoint, and Lua syntax drift. `just apply` additionally controls Hyprland autoreload, snapshots the old generated set, reloads, checks `hyprctl -j configerrors`, and restores the snapshot on failure.

The generated aggregate module always sets `misc:disable_autoreload = true`. After installation, use `just apply` or `just rollback` for explicit reloads.

## Escape hatch

Use the hand-maintained `config/manual.lua` for unsupported Hyprland APIs, complex shell logic, permissions, device settings, gestures, plugins, or Noctalia configuration. It is loaded before `config.generated`; the compiler only checks its Lua syntax. The legacy `config/variables.lua` is retained only for `just migrate-variables` and is not an active source.
