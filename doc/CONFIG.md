<!-- GENERATED FILE. DO NOT EDIT. -->
<!-- Sources: config/*.toml and the schema registry -->
<!-- Content-SHA256: 593e229c60bc880a23e1394f672a90cd957d19a2ecf28a0d748382ede7d069ae -->

# TOML Configuration

This document is generated from the registered TOML schemas. Generated Lua is deployed under `$HYPRLAND_CONFIG_ROOT/config/generated/`.
Unlisted fields are intentionally unsupported and belong in `config/manual.lua`.

## Common metadata

Every domain file uses `[meta]` with `schema = "1"`, `target_hyprland = ">=0.55.0"`, and a non-empty `profile`.
Missing source files produce empty generated modules; they do not add defaults.

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

## Field registry

### monitors.toml

`output` is required. Optional fields: `mode`, `position` (`"auto"` or `{ x, y }`), `scale` (`"auto"` or a number >= 0.25), `disabled`, `transform` (`normal`, `90`, `180`, `270`, and flipped variants), and `vrr` (`off`, `on`, `fullscreen`).

### workspaces.toml

`workspace` is required. Optional fields: `monitor`, `default`, `persistent`, and `layout`.

### input.toml

Keyboard fields: `layout`, `variant`, `model`, `options`, `rules`, `repeat_rate`, `repeat_delay`, `numlock_by_default`, `resolve_binds_by_sym`.

Mouse fields: `follow`, `follow_threshold`, `focus_on_close`, `mouse_refocus`, `float_switch_override_focus`, `sensitivity`, `accel_profile`, `force_no_accel`, `rotation`, `left_handed`, `scroll_method`, `scroll_button`, `scroll_button_lock`, `scroll_points`, `scroll_factor`, `natural_scroll`, `special_fallthrough`, `off_window_axis_events`, `emulate_discrete_scroll`, `follow_mouse_shrink`.

Touchpad, device-specific settings, and gestures are not in this schema.

### rules.toml

Window matchers: `class, content, float, focus, fullscreen, fullscreen_state_client, fullscreen_state_internal, group, initial_class, initial_title, modal, namespace, pin, tag, title, workspace, xdg_tag, xwayland`.
Layer matchers: `namespace`.
Rules require unique names, at least one matcher, and at least one effect. Matcher strings are interpreted by Hyprland; the compiler does not implement regex semantics.

Window effects: `allows_input, animation, border_size, center, confine_pointer, content, decorate, dim_around, float, focus_on_activate, force_rgbx, fullscreen, fullscreen_state, group, idle_inhibit, immediate, keep_aspect_ratio, max_size, maximize, min_size, monitor, move, nearest_neighbor, no_anim, no_blur, no_close_for, no_dim, no_focus, no_follow_mouse, no_initial_focus, no_max_size, no_screen_share, no_shadow, no_shortcuts_inhibit, no_vrr, opacity, opaque, persistent_size, pin, pseudo, render_unfocused, rounding, rounding_power, scroll_mouse, scroll_touchpad, scrolling_width, size, stay_focused, suppress_event, sync_fullscreen, tag, tile, workspace, xray`.
Layer effects: `above_lock, animation, blur, blur_popups, dim_around, ignore_alpha, no_anim, no_screen_share, order, xray`.

### environment.toml

`[environment]` contains non-empty environment names and string values. Values are literal: there is no shell expansion, command substitution, or implicit import from the current shell.

### autostart.toml

Each `exec_once` entry has a unique `name` and a non-empty `command` argv array. The executable must be in the compiler allowlist; shell operators and command substitution are rejected.

## Escape hatch

Use the hand-maintained `config/manual.lua` for unsupported Hyprland APIs, complex shell logic, permissions, device settings, gestures, plugins, or Noctalia configuration. It is loaded before `config.generated`; the compiler only checks its Lua syntax.
