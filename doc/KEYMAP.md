<!-- GENERATED FILE. DO NOT EDIT. -->
<!-- Source: config/keymap.toml -->
<!-- Content-SHA256: 5d0a8b62d58b561791319399a7efe2a14b25546b3e4baa76aa55fe2439999643 -->

# Keymap

This file is generated from [`config/keymap.toml`](../config/keymap.toml). The keymap targets Hyprland >= 0.55.0 with the CachyOS Hypr/Noctalia profile.

The generated Lua is deployed to `$HYPRLAND_CONFIG_ROOT/config/binds.lua`. Set `HYPRLAND_CONFIG_ROOT` once in the workstation environment, then use the Justfile commands to generate, check, apply, or roll back the deployment.

## Chord syntax

A chord is one optional modifier and one key: `mod+h`, `send+1`, `Shift+h`, or `XF86AudioRaiseVolume`. `mod` expands to the configured `SUPER` modifier and `send` expands to `ALT`. Missing TOML fields mean that no binding is generated.

Workspace digits use physical key codes so the number row remains stable across layouts: `1..9,0` compile to `code:10..19`.

## Supported actions

| Section | Action | Meaning |
| --- | --- | --- |
| `window` | `focus` | focus by direction or move a window |
| `window` | `close` | close the active window |
| `window` | `fullscreen` | toggle fullscreen |
| `window` | `maximize` | maximize the active scrolling column to its configured width |
| `window` | `toggle_float` | toggle floating state |
| `window` | `split_direction` | toggle the split direction |
| `window` | `cycle_window` | cycle to the next window |
| `workspace` | `switch` | focus a global workspace |
| `workspace` | `move_follow` | move the active window and follow it |
| `workspace` | `adjacent_focus` | focus the adjacent workspace |
| `workspace` | `adjacent_move` | move and follow to the adjacent workspace |
| `workspace` | `scratchpad_toggle` | toggle the Scratchpad |
| `workspace` | `scratchpad_move` | move the active window to the Scratchpad |
| `monitor` | `focus_next` | focus the next monitor |
| `monitor` | `move_next_follow` | move and follow to the next monitor |
| `application` | `terminal` | launch the configured terminal |
| `application` | `file_manager` | launch the configured file manager |
| `application` | `browser` | launch the configured browser |
| `application` | `calculator` | launch the configured calculator |
| `application` | `system_monitor` | launch the configured system monitor |
| `noctalia` | `launcher` | toggle the Noctalia launcher |
| `noctalia` | `window_switcher` | toggle the Noctalia window switcher |
| `noctalia` | `clipboard` | toggle the Noctalia clipboard |
| `noctalia` | `notifications` | toggle Noctalia notifications |
| `noctalia` | `control_center` | toggle the Noctalia control center |
| `noctalia` | `settings` | toggle Noctalia settings |
| `noctalia` | `emoji` | toggle the Noctalia emoji picker |
| `noctalia` | `wallpaper` | toggle the Noctalia wallpaper picker |
| `noctalia` | `lock` | lock through Noctalia |
| `noctalia` | `session_menu` | toggle the Noctalia session menu |
| `hardware` | `volume_up` | increase volume through Noctalia IPC |
| `hardware` | `volume_down` | decrease volume through Noctalia IPC |
| `hardware` | `mute` | toggle mute through Noctalia IPC |
| `hardware` | `play_pause` | toggle media playback through Noctalia IPC |
| `hardware` | `previous` | previous media item through Noctalia IPC |
| `hardware` | `next` | next media item through Noctalia IPC |
| `hardware` | `brightness_down` | decrease brightness through Noctalia IPC |
| `hardware` | `brightness_up` | increase brightness through Noctalia IPC |
| `utility` | `screenshot_region` | copy a region screenshot |
| `utility` | `screenshot_fullscreen` | copy a fullscreen screenshot |
| `utility` | `color_picker` | pick a color with Hyprpicker |
| `utility` | `zoom_out` | decrease scrolling column size by 0.3 |
| `utility` | `zoom_in` | increase scrolling column size by 0.3 |
| `pointer` | `move` | move the active window with the pointer |
| `pointer` | `resize` | resize the active window with the pointer |
| `adjust` | `enter` | enter Adjust mode |
| `adjust` | `exit` | leave Adjust mode |
| `adjust` | `reorder` | reorder the active window |
| `adjust` | `resize` | resize the active window by 40px |
| `extra.exec` | `named command` | run an allowlisted process or shell command |

## Current bindings

| Mode | Section | Action | Chord |
| --- | --- | --- | --- |
| `normal` | `window` | `close` | `SUPER + Q` |
| `normal` | `window` | `cycle_window` | `ALT + TAB` |
| `normal` | `window` | `focus` | `SUPER + H` |
| `normal` | `window` | `focus` | `SUPER + J` |
| `normal` | `window` | `focus` | `SUPER + K` |
| `normal` | `window` | `focus` | `SUPER + L` |
| `normal` | `window` | `fullscreen` | `SUPER + F` |
| `normal` | `window` | `maximize` | `SUPER + D` |
| `normal` | `window` | `split_direction` | `SUPER + G` |
| `normal` | `window` | `toggle_float` | `SUPER + T` |
| `normal` | `workspace` | `adjacent_focus` | `SUPER + [` |
| `normal` | `workspace` | `adjacent_focus` | `SUPER + ]` |
| `normal` | `workspace` | `adjacent_move` | `ALT + [` |
| `normal` | `workspace` | `adjacent_move` | `ALT + ]` |
| `normal` | `workspace` | `move_follow` | `ALT + code:10` |
| `normal` | `workspace` | `move_follow` | `ALT + code:11` |
| `normal` | `workspace` | `move_follow` | `ALT + code:12` |
| `normal` | `workspace` | `move_follow` | `ALT + code:13` |
| `normal` | `workspace` | `move_follow` | `ALT + code:14` |
| `normal` | `workspace` | `move_follow` | `ALT + code:15` |
| `normal` | `workspace` | `move_follow` | `ALT + code:16` |
| `normal` | `workspace` | `move_follow` | `ALT + code:17` |
| `normal` | `workspace` | `move_follow` | `ALT + code:18` |
| `normal` | `workspace` | `move_follow` | `ALT + code:19` |
| `normal` | `workspace` | `scratchpad_move` | `ALT + S` |
| `normal` | `workspace` | `scratchpad_toggle` | `SUPER + S` |
| `normal` | `workspace` | `switch` | `SUPER + code:10` |
| `normal` | `workspace` | `switch` | `SUPER + code:11` |
| `normal` | `workspace` | `switch` | `SUPER + code:12` |
| `normal` | `workspace` | `switch` | `SUPER + code:13` |
| `normal` | `workspace` | `switch` | `SUPER + code:14` |
| `normal` | `workspace` | `switch` | `SUPER + code:15` |
| `normal` | `workspace` | `switch` | `SUPER + code:16` |
| `normal` | `workspace` | `switch` | `SUPER + code:17` |
| `normal` | `workspace` | `switch` | `SUPER + code:18` |
| `normal` | `workspace` | `switch` | `SUPER + code:19` |
| `normal` | `monitor` | `focus_next` | `SUPER + O` |
| `normal` | `monitor` | `move_next_follow` | `ALT + O` |
| `normal` | `application` | `browser` | `SUPER + B` |
| `normal` | `application` | `calculator` | `SUPER + C` |
| `normal` | `application` | `file_manager` | `SUPER + E` |
| `normal` | `application` | `system_monitor` | `SUPER + U` |
| `normal` | `application` | `terminal` | `SUPER + ENTER` |
| `normal` | `noctalia` | `clipboard` | `SUPER + V` |
| `normal` | `noctalia` | `control_center` | `SUPER + X` |
| `normal` | `noctalia` | `emoji` | `SUPER + .` |
| `normal` | `noctalia` | `launcher` | `SUPER + SPACE` |
| `universal` | `noctalia` | `lock` | `SUPER + BACKSPACE` |
| `normal` | `noctalia` | `notifications` | `SUPER + N` |
| `universal` | `noctalia` | `session_menu` | `SUPER + ESC` |
| `normal` | `noctalia` | `settings` | `SUPER + ,` |
| `normal` | `noctalia` | `wallpaper` | `SUPER + W` |
| `normal` | `noctalia` | `window_switcher` | `SUPER + TAB` |
| `universal` | `hardware` | `brightness_down` | `XF86MonBrightnessDown` |
| `universal` | `hardware` | `brightness_up` | `XF86MonBrightnessUp` |
| `universal` | `hardware` | `mute` | `XF86AudioMute` |
| `universal` | `hardware` | `next` | `XF86AudioNext` |
| `universal` | `hardware` | `play_pause` | `XF86AudioPlay` |
| `universal` | `hardware` | `previous` | `XF86AudioPrev` |
| `universal` | `hardware` | `volume_down` | `XF86AudioLowerVolume` |
| `universal` | `hardware` | `volume_up` | `XF86AudioRaiseVolume` |
| `normal` | `utility` | `color_picker` | `SUPER + P` |
| `normal` | `utility` | `screenshot_fullscreen` | `SHIFT + PRINT` |
| `normal` | `utility` | `screenshot_region` | `PRINT` |
| `normal` | `utility` | `zoom_in` | `SUPER + =` |
| `normal` | `utility` | `zoom_out` | `SUPER + -` |
| `normal` | `pointer` | `move` | `SUPER + mouse:272` |
| `normal` | `pointer` | `resize` | `SUPER + mouse:273` |
| `normal` | `adjust` | `enter` | `SUPER + A` |
| `adjust` | `adjust` | `exit` | `ENTER` |
| `adjust` | `adjust` | `exit` | `ESC` |
| `adjust` | `adjust` | `reorder` | `H` |
| `adjust` | `adjust` | `reorder` | `J` |
| `adjust` | `adjust` | `reorder` | `K` |
| `adjust` | `adjust` | `reorder` | `L` |
| `adjust` | `adjust` | `resize` | `SHIFT + H` |
| `adjust` | `adjust` | `resize` | `SHIFT + J` |
| `adjust` | `adjust` | `resize` | `SHIFT + K` |
| `adjust` | `adjust` | `resize` | `SHIFT + L` |

## Adjust mode

`mod+a` enters the finite Adjust mode. `Esc` and `Enter` leave it. `h/j/k/l` reorder windows; `Shift+h/j/k/l` resize by 40px. These bindings repeat. Other keys are consumed and leave the mode active.

## Common special keys

| Input spelling | Compiled spelling |
| --- | --- |
| `Esc`, `Enter`, `Space`, `Tab`, `Backspace`, `Print` | `Escape`, `Return`, `SPACE`, `Tab`, `BackSpace`, `Print` |
| `-`, `=`, `[`, `]`, `,`, `.`, `/` | `minus`, `equal`, `bracketleft`, `bracketright`, `comma`, `period`, `slash` |
| `mouse:left`, `mouse:right` | `mouse:272`, `mouse:273` |
| `XF86AudioRaiseVolume` | unchanged |
| `F1`-`F12` | valid spare keys; intentionally unbound |

Pointer bindings use the Hyprland mouse option and button numbers. XF86 hardware keys are universal bindings and remain available while the session is locked and in Adjust mode. No workspace is fixed to a monitor; numbered workspaces remain global.
