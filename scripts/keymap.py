#!/usr/bin/env python3
"""Validate and render the TOML-driven Hyprland keymap domain."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from string import ascii_uppercase
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
KEYMAP_PATH = ROOT / "config" / "keymap.toml"

SECTION_ORDER = (
    "window",
    "workspace",
    "monitor",
    "application",
    "noctalia",
    "hardware",
    "utility",
    "pointer",
    "adjust",
    "extra",
)

SECTION_ACTIONS: dict[str, tuple[str, ...]] = {
    "window": (
        "focus",
        "close",
        "fullscreen",
        "maximize",
        "toggle_float",
        "split_direction",
        "cycle_window",
    ),
    "workspace": (
        "switch",
        "move_follow",
        "adjacent_focus",
        "adjacent_move",
        "scratchpad_toggle",
        "scratchpad_move",
    ),
    "monitor": ("focus_next", "move_next_follow"),
    "application": (
        "terminal",
        "file_manager",
        "browser",
        "calculator",
        "system_monitor",
    ),
    "noctalia": (
        "launcher",
        "window_switcher",
        "clipboard",
        "notifications",
        "control_center",
        "settings",
        "emoji",
        "wallpaper",
        "lock",
        "session_menu",
    ),
    "hardware": (
        "volume_up",
        "volume_down",
        "mute",
        "play_pause",
        "previous",
        "next",
        "brightness_down",
        "brightness_up",
    ),
    "utility": (
        "screenshot_region",
        "screenshot_fullscreen",
        "color_picker",
        "zoom_out",
        "zoom_in",
    ),
    "pointer": ("move", "resize"),
    "adjust": ("enter", "exit", "reorder", "resize"),
}

META_FIELDS = {"schema", "target_hyprland", "profile"}
MODIFIER_FIELDS = {"mod", "send"}
EXTRA_FIELDS = {"exec"}
ADJUST_FIELDS = {"enter", "exit", "reorder", "resize"}

MODIFIER_NAMES = {"SUPER", "ALT", "CTRL", "SHIFT"}
MODIFIER_ALIASES = {
    "mod": "mod",
    "send": "send",
    "super": "SUPER",
    "alt": "ALT",
    "ctrl": "CTRL",
    "control": "CTRL",
    "shift": "SHIFT",
}
KEY_ALIASES = {
    "esc": "ESC",
    "escape": "ESC",
    "enter": "ENTER",
    "return": "ENTER",
    "space": "SPACE",
    "tab": "TAB",
    "backspace": "BACKSPACE",
    "print": "PRINT",
    "printscreen": "PRINT",
    "minus": "-",
    "equal": "=",
    "equals": "=",
    "comma": ",",
    "period": ".",
    "dot": ".",
    "slash": "/",
    "bracketleft": "[",
    "bracketright": "]",
    "leftbracket": "[",
    "rightbracket": "]",
    "mouse:left": "mouse:272",
    "mouse:right": "mouse:273",
    "mouse:middle": "mouse:274",
}
ALLOWED_EXECUTABLES = {
    "brightnessctl",
    "grim",
    "hypridle",
    "hyprlock",
    "hyprpaper",
    "hyprpicker",
    "noctalia",
    "notify-send",
    "noctalia-shell",
    "pamixer",
    "playerctl",
    "slurp",
    "systemctl",
    "true",
    "waybar",
    "wl-copy",
}
SHELL_WORDS = {"&&", "||", "|", ";", "&", ">", ">>", "<", "2>", "2>>"}
FORBIDDEN_EXEC_WORDS = {
    "dispatch",
    "dofile",
    "eval",
    "hyprctl",
    "keyword",
    "load",
    "require",
    "reload",
}
SINGLE_KEYS = set(ascii_uppercase) | set("0123456789-=[] ,./".replace(" ", ""))
SPECIAL_KEYS = {
    "ESC",
    "ENTER",
    "SPACE",
    "TAB",
    "BACKSPACE",
    "PRINT",
    "XF86AudioRaiseVolume",
    "XF86AudioLowerVolume",
    "XF86AudioMute",
    "XF86AudioPlay",
    "XF86AudioPrev",
    "XF86AudioNext",
    "XF86MonBrightnessDown",
    "XF86MonBrightnessUp",
}


class KeymapError(ValueError):
    """Validation errors collected from one keymap input."""

    def __init__(self, errors: Iterable[str]):
        if isinstance(errors, str):
            errors = (errors,)
        self.errors = tuple(dict.fromkeys(errors))
        super().__init__("\n".join(f"- {error}" for error in self.errors))


@dataclass(frozen=True)
class Chord:
    modifier: str | None
    key: str

    @property
    def canonical(self) -> str:
        return f"{self.modifier} + {self.key}" if self.modifier else self.key


@dataclass(frozen=True)
class Binding:
    section: str
    action: str
    chord: Chord
    mode: str
    path: str


@dataclass(frozen=True)
class ExtraExec:
    name: str
    chord: Chord
    command: str
    mode: str
    path: str


@dataclass(frozen=True)
class Keymap:
    source: Path
    source_hash: str
    data: dict[str, Any]
    bindings: tuple[Binding, ...]
    extra_exec: tuple[ExtraExec, ...]


def _is_table(value: object) -> bool:
    return isinstance(value, dict)


def _validate_string(value: object, path: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}: expected a non-empty string")
        return False
    return True


def _normalize_modifier(token: str, modifiers: dict[str, str], path: str) -> str | None:
    alias = MODIFIER_ALIASES.get(token.lower())
    if alias in ("mod", "send"):
        if alias not in modifiers:
            raise KeymapError((f"{path}: modifier alias {token!r} is not configured",))
        return modifiers[alias]
    return alias


def _normalize_key(token: str) -> str:
    lower = token.lower()
    if lower in KEY_ALIASES:
        return KEY_ALIASES[lower]
    if lower.startswith("xf86"):
        suffix = token[4:]
        if not suffix:
            return token
        return "XF86" + suffix[0].upper() + suffix[1:]
    if lower.startswith("mouse:"):
        return "mouse:" + token.split(":", 1)[1]
    if lower.startswith("code:"):
        return "code:" + token.split(":", 1)[1]
    if len(token) == 1 and token.isalpha():
        return token.upper()
    if token.isdigit() or token in {"-", "=", "[", "]", ",", ".", "/"}:
        return token
    return token


def normalize_chord(value: object, modifiers: dict[str, str], path: str = "chord") -> Chord:
    """Normalize a TOML chord and enforce one modifier plus one key."""

    if not isinstance(value, str):
        raise KeymapError((f"{path}: expected a chord string",))
    raw = value.strip()
    pieces = [piece.strip() for piece in raw.split("+")]
    if not raw or any(not piece for piece in pieces):
        raise KeymapError((f"{path}: malformed chord {value!r}",))
    if len(pieces) > 2:
        raise KeymapError((f"{path}: a chord has at most one modifier and one key",))

    modifier: str | None = None
    key_tokens: list[str] = []
    for piece in pieces:
        candidate = _normalize_modifier(piece, modifiers, path)
        if candidate is not None:
            if candidate not in MODIFIER_NAMES:
                raise KeymapError((f"{path}: unknown modifier {piece!r}",))
            if modifier is not None:
                raise KeymapError((f"{path}: a chord has more than one modifier",))
            modifier = candidate
        else:
            key_tokens.append(piece)
    if len(key_tokens) != 1:
        raise KeymapError((f"{path}: expected one non-modifier key",))
    key = _normalize_key(key_tokens[0])
    if key.lower() == "catchall":
        raise KeymapError((f"{path}: catchall is reserved for the generated Adjust mode",))
    if any(char.isspace() for char in key) or not key:
        raise KeymapError((f"{path}: invalid key {key!r}",))
    valid_function_key = key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12
    valid_mouse_key = key.startswith("mouse:") and key[6:].isdigit() and int(key[6:]) > 0
    valid_code_key = key.startswith("code:") and key[5:].isdigit() and int(key[5:]) > 0
    if not (key in SINGLE_KEYS or key in SPECIAL_KEYS or valid_function_key or valid_mouse_key or valid_code_key):
        raise KeymapError((f"{path}: unsupported key {key!r}; use a letter, F1-F12, special key, mouse:<number>, or code:<number>",))
    return Chord(modifier, key)


def _chords(value: object, path: str, modifiers: dict[str, str], errors: list[str]) -> list[Chord]:
    values = value if isinstance(value, list) else [value]
    if isinstance(value, list) and not value:
        errors.append(f"{path}: expected one or more chords")
        return []
    result: list[Chord] = []
    for index, item in enumerate(values):
        item_path = f"{path}[{index}]" if isinstance(value, list) else path
        try:
            result.append(normalize_chord(item, modifiers, item_path))
        except KeymapError as exc:
            errors.extend(exc.errors)
    return result


def _validate_command(command: object, path: str, errors: list[str]) -> None:
    if not _validate_string(command, path, errors):
        return
    assert isinstance(command, str)
    if "\x00" in command:
        errors.append(f"{path}: NUL bytes are not allowed")
        return
    if "$(" in command or "`" in command:
        errors.append(f"{path}: command substitution is not allowed")
        return
    try:
        words = shlex.split(command)
    except ValueError as exc:
        errors.append(f"{path}: invalid shell quoting ({exc})")
        return
    if not words:
        errors.append(f"{path}: command cannot be empty")
        return
    if words[0] in {"sh", "bash"}:
        if len(words) != 3 or words[1] != "-c":
            errors.append(f"{path}: shell commands must use sh -c '...' exactly")
            return
        shell = shlex.shlex(words[2], posix=True, punctuation_chars=";&|<>")
        shell.whitespace_split = True
        command_words = list(shell)
    else:
        shell = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
        shell.whitespace_split = True
        command_words = list(shell)
        if any(word in SHELL_WORDS for word in command_words):
            errors.append(f"{path}: shell operators require sh -c '...' and are not allowed in direct commands")
            return
    expects_executable = True
    for word in command_words:
        if word in SHELL_WORDS:
            expects_executable = True
            continue
        if expects_executable:
            if word not in ALLOWED_EXECUTABLES:
                errors.append(f"{path}: executable is not in the controlled process allowlist")
                break
            expects_executable = False
    for word in command_words:
        if word.lower() in FORBIDDEN_EXEC_WORDS or word.lower().startswith("hyprctl"):
            errors.append(f"{path}: raw Hyprland dispatch/control commands are not allowed")
            break


def _mode_for(section: str, action: str) -> str:
    if section == "hardware":
        return "universal"
    if section == "noctalia" and action in {"lock", "session_menu"}:
        return "universal"
    if section == "adjust" and action != "enter":
        return "adjust"
    return "normal"


def _workspace_code(chord: Chord, action: str) -> Chord:
    if action not in {"switch", "move_follow"} or chord.key not in "1234567890":
        return chord
    code = 19 if chord.key == "0" else 9 + int(chord.key)
    return Chord(chord.modifier, f"code:{code}")


def validate(data: object, source: Path = KEYMAP_PATH) -> Keymap:
    """Validate parsed TOML and return deterministic, normalized bindings."""

    errors: list[str] = []
    if not _is_table(data):
        raise KeymapError(("root: expected a TOML table",))
    assert isinstance(data, dict)
    allowed_root = {"meta", "modifiers", *SECTION_ACTIONS, "extra"}
    for key in data:
        if key not in allowed_root:
            errors.append(f"{key}: unknown top-level section")

    meta = data.get("meta")
    if not _is_table(meta):
        errors.append("meta: required table is missing")
        meta = {}
    assert isinstance(meta, dict)
    for key in meta:
        if key not in META_FIELDS:
            errors.append(f"meta.{key}: unknown field")
    for key in META_FIELDS:
        if key not in meta:
            errors.append(f"meta.{key}: required field is missing")
        elif not _validate_string(meta[key], f"meta.{key}", errors):
            continue
    if meta.get("schema") != "1":
        errors.append("meta.schema: must be \"1\"")

    modifier_table = data.get("modifiers")
    if not _is_table(modifier_table):
        errors.append("modifiers: required table is missing")
        modifier_table = {}
    assert isinstance(modifier_table, dict)
    for key in modifier_table:
        if key not in MODIFIER_FIELDS:
            errors.append(f"modifiers.{key}: unknown field")
    modifiers: dict[str, str] = {}
    for key in MODIFIER_FIELDS:
        value = modifier_table.get(key)
        if not _validate_string(value, f"modifiers.{key}", errors):
            continue
        assert isinstance(value, str)
        normalized = value.strip().upper()
        if normalized not in MODIFIER_NAMES:
            errors.append(f"modifiers.{key}: expected one of SUPER, ALT, CTRL, SHIFT")
        elif normalized == "SHIFT":
            errors.append(f"modifiers.{key}: SHIFT is not a primary modifier alias")
        else:
            modifiers[key] = normalized
    if len(set(modifiers.values())) != len(modifiers):
        errors.append("modifiers: mod and send must expand to different modifiers")

    bindings: list[Binding] = []
    for section, actions in SECTION_ACTIONS.items():
        section_value = data.get(section)
        if section_value is None:
            continue
        if not _is_table(section_value):
            errors.append(f"{section}: expected a TOML table")
            continue
        assert isinstance(section_value, dict)
        allowed_fields = ADJUST_FIELDS if section == "adjust" else set(actions)
        for action in section_value:
            if action not in allowed_fields:
                errors.append(f"{section}.{action}: unknown action")
        for action in actions:
            if action not in section_value:
                continue
            value = section_value[action]
            if isinstance(value, dict):
                errors.append(f"{section}.{action}: expected a chord or chord array")
                continue
            action_chords = _chords(value, f"{section}.{action}", modifiers, errors)
            for chord in action_chords:
                if section == "window" and action == "focus" and chord.key not in {"H", "J", "K", "L"}:
                    errors.append(f"{section}.{action}: keys must be h, j, k, or l so their directions are unambiguous")
                bindings.append(
                    Binding(
                        section,
                        action,
                        _workspace_code(chord, action),
                        _mode_for(section, action),
                        f"{section}.{action}",
                    )
                )

    extra_exec: list[ExtraExec] = []
    extra = data.get("extra")
    if extra is not None:
        if not _is_table(extra):
            errors.append("extra: expected a TOML table")
        else:
            assert isinstance(extra, dict)
            for key in extra:
                if key not in EXTRA_FIELDS:
                    errors.append(f"extra.{key}: unknown field")
            exec_table = extra.get("exec")
            if exec_table is not None:
                if not _is_table(exec_table):
                    errors.append("extra.exec: expected a table of named commands")
                else:
                    assert isinstance(exec_table, dict)
                    for name, entry in exec_table.items():
                        path = f"extra.exec.{name}"
                        if not isinstance(name, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", name) is None:
                            errors.append(f"{path}: command name must be a non-empty identifier")
                            continue
                        if not _is_table(entry):
                            errors.append(f"{path}: expected a table")
                            continue
                        assert isinstance(entry, dict)
                        for key in entry:
                            if key not in {"chord", "command", "mode"}:
                                errors.append(f"{path}.{key}: unknown field")
                        if "chord" not in entry:
                            errors.append(f"{path}.chord: required field is missing")
                            continue
                        if "command" not in entry:
                            errors.append(f"{path}.command: required field is missing")
                            continue
                        mode = entry.get("mode", "normal")
                        if mode not in {"normal", "universal"}:
                            errors.append(f"{path}.mode: expected normal or universal")
                        _validate_command(entry["command"], f"{path}.command", errors)
                        try:
                            chord = normalize_chord(entry["chord"], modifiers, f"{path}.chord")
                        except KeymapError as exc:
                            errors.extend(exc.errors)
                        else:
                            extra_exec.append(ExtraExec(name, chord, entry["command"], mode, path))

    if "adjust" not in data or not isinstance(data.get("adjust"), dict):
        errors.append("adjust: required table must define the finite Adjust mode")
    else:
        adjust = data["adjust"]
        assert isinstance(adjust, dict)
        if "enter" not in adjust:
            errors.append("adjust.enter: required entry is missing")
        if "exit" not in adjust:
            errors.append("adjust.exit: required Esc and Enter exit chords are missing")
        else:
            exit_chords = _chords(adjust["exit"], "adjust.exit", modifiers, errors)
            exit_keys = {chord.key for chord in exit_chords if chord.modifier is None}
            if not {"ESC", "ENTER"}.issubset(exit_keys):
                errors.append("adjust.exit: both Esc and Enter must be present without modifiers")
        for action, expected in (("reorder", {"H", "J", "K", "L"}), ("resize", {"H", "J", "K", "L"})):
            if action not in adjust:
                errors.append(f"adjust.{action}: required h/j/k/l entries are missing")
                continue
            values = _chords(adjust[action], f"adjust.{action}", modifiers, errors)
            keys = {item.key for item in values}
            if keys != expected:
                errors.append(f"adjust.{action}: must contain exactly h, j, k, and l")
            if action == "resize" and any(item.modifier != "SHIFT" for item in values):
                errors.append("adjust.resize: every chord must use Shift as its only modifier")
            if action == "reorder" and any(item.modifier is not None for item in values):
                errors.append("adjust.reorder: every chord must be unmodified")

    all_bindings = [*bindings, *(Binding("extra", item.name, item.chord, item.mode, item.path) for item in extra_exec)]
    seen: dict[tuple[str, str], Binding] = {}
    universal: dict[str, Binding] = {}
    for binding in all_bindings:
        scope_key = (binding.mode, binding.chord.canonical)
        if scope_key in seen:
            other = seen[scope_key]
            errors.append(f"{binding.path}: duplicate chord {binding.chord.canonical!r}; already used by {other.path}")
        else:
            seen[scope_key] = binding
        if binding.mode == "universal":
            if binding.chord.canonical in universal:
                continue
            universal[binding.chord.canonical] = binding
    for binding in all_bindings:
        if binding.mode != "universal" and binding.chord.canonical in universal:
            errors.append(
                f"{binding.path}: chord {binding.chord.canonical!r} conflicts with universal binding "
                f"{universal[binding.chord.canonical].path}"
            )

    if errors:
        raise KeymapError(errors)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    bindings.sort(key=lambda item: (SECTION_ORDER.index(item.section), item.action, item.mode, item.chord.canonical))
    extra_exec.sort(key=lambda item: (item.mode, item.chord.canonical, item.name))
    return Keymap(source, source_hash, data, tuple(bindings), tuple(extra_exec))


def load_keymap(path: Path = KEYMAP_PATH) -> Keymap:
    try:
        import tomllib

        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except ModuleNotFoundError as exc:
        raise KeymapError(("Python 3.11+ is required because the compiler uses the standard-library tomllib",)) from exc
    except FileNotFoundError as exc:
        raise KeymapError((f"{path}: file does not exist",)) from exc
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise KeymapError((f"{path}: invalid TOML ({exc})",)) from exc
    return validate(data, path)


def _lua_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


HYPRLAND_KEY_NAMES = {
    "ENTER": "Return",
    "ESC": "Escape",
    "TAB": "Tab",
    "BACKSPACE": "BackSpace",
    "PRINT": "Print",
    "-": "minus",
    "=": "equal",
    "[": "bracketleft",
    "]": "bracketright",
    ",": "comma",
    ".": "period",
    "/": "slash",
}


def _hyprland_key_name(key: str) -> str:
    """Return the key spelling accepted by Hyprland's bind parser."""

    return HYPRLAND_KEY_NAMES.get(key, key)


def _bind_chord(chord: Chord) -> str:
    key = _hyprland_key_name(chord.key)
    return f"{chord.modifier} + {key}" if chord.modifier else key


def _workspace_value(binding: Binding) -> str:
    if binding.chord.key.startswith("code:"):
        return binding.chord.key[5:]
    return binding.chord.key


def _noctalia_command(action: str) -> str:
    commands = {
        "launcher": "noctalia msg panel-toggle launcher",
        "window_switcher": "noctalia msg window-switcher",
        "clipboard": "noctalia msg panel-toggle clipboard",
        "notifications": "noctalia msg panel-toggle control-center notifications",
        "control_center": "noctalia msg panel-toggle control-center",
        "settings": "noctalia msg settings-toggle",
        "emoji": "noctalia msg panel-toggle launcher /emo",
        "wallpaper": "noctalia msg panel-toggle wallpaper",
        "lock": "noctalia msg session lock",
        "session_menu": "noctalia msg panel-toggle session",
    }
    return commands[action]


def _dispatcher(binding: Binding) -> str:
    section, action, key = binding.section, binding.action, binding.chord.key
    if section == "window":
        if action == "focus":
            direction = {"H": "left", "J": "down", "K": "up", "L": "right"}[key]
            return f'hl.dsp.focus({{ direction = "{direction}" }})'
        if action == "maximize":
            # The scrolling layout has no core maximize dispatcher. This is the
            # same layout-native expansion used by the CachyOS profile.
            return (
                "function()\n"
                '\thl.dispatch(hl.dsp.layout("colresize +conf"))\n'
                '\thl.dispatch(hl.dsp.layout("focus r"))\n'
                '\thl.dispatch(hl.dsp.layout("focus l"))\n'
                "end"
            )
        return {
            "close": "hl.dsp.window.close()",
            "fullscreen": 'hl.dsp.window.fullscreen({ mode = "fullscreen", action = "toggle" })',
            "toggle_float": 'hl.dsp.window.float({ action = "toggle" })',
            "split_direction": 'hl.dsp.layout("togglesplit")',
            "cycle_window": "hl.dsp.window.cycle_next({ next = true })",
        }[action]
    if section == "workspace":
        if action in {"switch", "move_follow"}:
            workspace = _workspace_value(binding)
            if action == "switch":
                return f'hl.dsp.focus({{ workspace = "{workspace}" }})'
            return f'hl.dsp.window.move({{ workspace = "{workspace}", follow = true }})'
        if action == "adjacent_focus":
            return f'hl.dsp.focus({{ workspace = "{"e-1" if key == "[" else "e+1"}" }})'
        if action == "adjacent_move":
            direction = "e-1" if key == "[" else "e+1"
            return f'hl.dsp.window.move({{ workspace = "{direction}", follow = true }})'
        if action == "scratchpad_toggle":
            return 'hl.dsp.workspace.toggle_special("scratchpad")'
        return 'hl.dsp.window.move({ workspace = "special:scratchpad" })'
    if section == "monitor":
        if action == "focus_next":
            return 'hl.dsp.focus({ monitor = "+1" })'
        return 'hl.dsp.window.move({ monitor = "+1", follow = true })'
    if section == "application":
        return f"hl.dsp.exec_cmd(variables.commands.{action})"
    if section == "noctalia":
        return f"hl.dsp.exec_cmd({_lua_string(_noctalia_command(action))})"
    if section == "hardware":
        commands = {
            "volume_up": "noctalia msg volume-up",
            "volume_down": "noctalia msg volume-down",
            "mute": "noctalia msg volume-mute",
            "play_pause": "noctalia msg media toggle",
            "previous": "noctalia msg media previous",
            "next": "noctalia msg media next",
            "brightness_down": "noctalia msg brightness-down",
            "brightness_up": "noctalia msg brightness-up",
        }
        return f"hl.dsp.exec_cmd({_lua_string(commands[action])})"
    if section == "utility":
        commands = {
            "screenshot_region": 'sh -c \'grim -g "$(slurp)" - | wl-copy\'',
            "screenshot_fullscreen": "grim - | wl-copy",
            "color_picker": "hyprpicker -a",
        }
        if action in commands:
            return f"hl.dsp.exec_cmd({_lua_string(commands[action])})"
        return f'hl.dsp.layout("colresize {"-0.3" if action == "zoom_out" else "+0.3"}")'
    if section == "pointer":
        return "hl.dsp.window.drag()" if action == "move" else "hl.dsp.window.resize()"
    if section == "adjust":
        if action == "enter":
            return 'hl.dsp.submap("adjust")'
        if action == "exit":
            return 'hl.dsp.submap("reset")'
        if action == "reorder":
            direction = {"H": "left", "J": "down", "K": "up", "L": "right"}[key]
            return f'hl.dsp.window.swap({{ direction = "{direction}" }})'
        deltas = {"H": ("-40", "0"), "J": ("0", "40"), "K": ("0", "-40"), "L": ("40", "0")}
        x, y = deltas[key]
        return f'hl.dsp.window.resize({{ x = {x}, y = {y}, relative = true }})'
    if section == "extra":
        raise AssertionError("extra commands are rendered separately")
    raise AssertionError(f"unhandled action: {section}.{action}")


def _render_binding(binding: Binding) -> str:
    expression = _dispatcher(binding)
    if binding.mode == "adjust":
        return _render_submap_binding(binding, expression)
    options: list[str] = []
    if binding.section == "hardware":
        options.append("locked = true")
        if binding.action in {"volume_up", "volume_down", "brightness_down", "brightness_up"}:
            options.append("repeating = true")
    if binding.mode == "universal":
        options.append("submap_universal = true")
    option_text = f", {{ {', '.join(options)} }}" if options else ""
    return f'hl.bind({_lua_string(_bind_chord(binding.chord))}, {expression}{option_text})'


def _render_submap_binding(binding: Binding, expression: str) -> str:
    key = _bind_chord(binding.chord)
    repeated = binding.action in {"reorder", "resize"}
    options = ", { repeating = true }" if repeated else ""
    return f'hl.bind({_lua_string(key)}, {expression}{options})'


def _render_extra_exec(item: ExtraExec) -> str:
    options = ", { submap_universal = true }" if item.mode == "universal" else ""
    return f'hl.bind({_lua_string(_bind_chord(item.chord))}, hl.dsp.exec_cmd({_lua_string(item.command)}){options})'


def render_lua(keymap: Keymap) -> str:
    lines = [
        "-- GENERATED FILE. DO NOT EDIT.",
        "-- Source: config/keymap.toml",
        f"-- Content-SHA256: {keymap.source_hash}",
        "-- Target: Hyprland >= 0.55.0, CachyOS Hypr/Noctalia profile",
        "",
        'local variables = require("config.generated.variables")',
        "",
        "-- Configuration reload is controlled by the generated aggregate module.",
    ]
    current_section: str | None = None
    adjust_open = False
    for binding in keymap.bindings:
        if binding.section != current_section:
            current_section = binding.section
            lines.extend([f"-- {current_section}", ""])
        if binding.mode == "adjust":
            if not adjust_open:
                lines.append('hl.define_submap("adjust", function()')
                adjust_open = True
            lines.extend(f"\t{line}" for line in _render_submap_binding(binding, _dispatcher(binding)).splitlines())
        else:
            lines.append(_render_binding(binding))
        lines.append("")
    if adjust_open:
        lines.append('\thl.bind("catchall", hl.dsp.no_op(), { ignore_mods = true })')
        lines.extend(["end)", ""])
    if keymap.extra_exec:
        lines.extend(["-- extra.exec", ""])
        for item in keymap.extra_exec:
            lines.append(_render_extra_exec(item))
            lines.append("")
    lines.extend(["-- Adjust mode consumes otherwise-unbound keys and stays active until Esc or Enter.", ""])
    return "\n".join(lines).rstrip() + "\n"


def _display_chord(binding: Binding) -> str:
    return binding.chord.canonical


def render_doc(keymap: Keymap) -> str:
    lines = [
        "<!-- GENERATED FILE. DO NOT EDIT. -->",
        "<!-- Source: config/keymap.toml -->",
        f"<!-- Content-SHA256: {keymap.source_hash} -->",
        "",
        "# Keymap",
        "",
        "This file is generated from [`config/keymap.toml`](../config/keymap.toml). "
        "The keymap targets Hyprland >= 0.55.0 with the CachyOS Hypr/Noctalia profile.",
        "",
        "The generated Lua is deployed to `$HYPRLAND_CONFIG_ROOT/config/generated/binds.lua`. "
        "Set `HYPRLAND_CONFIG_ROOT` once in the workstation environment, then use the "
        "Justfile commands to generate, check, apply, or roll back the deployment.",
        "",
        "## Chord syntax",
        "",
        "A chord is one optional modifier and one key: `mod+h`, `send+1`, `Shift+h`, "
        "or `XF86AudioRaiseVolume`. `mod` expands to the configured `SUPER` modifier and "
        "`send` expands to `ALT`. Missing TOML fields mean that no binding is generated.",
        "",
        "## TOML structure",
        "",
        "`[meta]` is required and must contain exactly `schema = \"1\"`, a non-empty `target_hyprland`, and a non-empty `profile`. "
        "`[modifiers]` is required and must define distinct `mod` and `send` values. Each value is one of `SUPER`, `ALT`, or `CTRL`; "
        "`SHIFT` cannot be used as a primary alias, but it is valid directly in a chord.",
        "",
        "All action sections are optional. An action value is either one chord string or a non-empty array of chord strings. "
        "Unknown sections and action names are rejected. The `[adjust]` table is the one exception: it is required and must define "
        "`enter`, `exit`, `reorder`, and `resize`.",
        "",
        "A chord has at most one modifier and one key. Modifier names are case-insensitive; supported modifiers are `mod`, `send`, `SUPER`, `ALT`, `CTRL`, `Control`, and `Shift`. "
        "Supported keys are `A`-`Z`, `0`-`9`, `-`, `=`, `[`, `]`, `,`, `.`, `/`, `F1`-`F12`, the common special keys below, "
        "`mouse:<number>`, and `code:<number>` with a positive number. `catchall` is reserved by Adjust mode.",
        "",
        "Workspace digits use physical key codes so the number row remains stable across layouts: "
        "`1..9,0` compile to `code:10..19`.",
        "",
        "For `workspace.switch` and `workspace.move_follow` only, the compiled workspace value is the digit itself (`1`-`9` or `0`), "
        "while the key is compiled to the physical code. Other workspace selectors are generated literally.",
        "",
        "## Supported actions",
        "",
        "| Section | Action | Meaning |",
        "| --- | --- | --- |",
    ]
    descriptions = {
        "focus": "focus by direction or move a window",
        "close": "close the active window",
        "fullscreen": "toggle fullscreen",
        "maximize": "maximize the active scrolling column to its configured width",
        "toggle_float": "toggle floating state",
        "split_direction": "toggle the split direction",
        "cycle_window": "cycle to the next window",
        "switch": "focus a global workspace",
        "move_follow": "move the active window and follow it",
        "adjacent_focus": "focus the adjacent workspace",
        "adjacent_move": "move and follow to the adjacent workspace",
        "scratchpad_toggle": "toggle the Scratchpad",
        "scratchpad_move": "move the active window to the Scratchpad",
        "focus_next": "focus the next monitor",
        "move_next_follow": "move and follow to the next monitor",
        "terminal": "launch the configured terminal",
        "file_manager": "launch the configured file manager",
        "browser": "launch the configured browser",
        "calculator": "launch the configured calculator",
        "system_monitor": "launch the configured system monitor",
        "launcher": "toggle the Noctalia launcher",
        "window_switcher": "toggle the Noctalia window switcher",
        "clipboard": "toggle the Noctalia clipboard",
        "notifications": "toggle Noctalia notifications",
        "control_center": "toggle the Noctalia control center",
        "settings": "toggle Noctalia settings",
        "emoji": "toggle the Noctalia emoji picker",
        "wallpaper": "toggle the Noctalia wallpaper picker",
        "lock": "lock through Noctalia",
        "session_menu": "toggle the Noctalia session menu",
        "volume_up": "increase volume through Noctalia IPC",
        "volume_down": "decrease volume through Noctalia IPC",
        "mute": "toggle mute through Noctalia IPC",
        "play_pause": "toggle media playback through Noctalia IPC",
        "previous": "previous media item through Noctalia IPC",
        "next": "next media item through Noctalia IPC",
        "brightness_down": "decrease brightness through Noctalia IPC",
        "brightness_up": "increase brightness through Noctalia IPC",
        "screenshot_region": "copy a region screenshot",
        "screenshot_fullscreen": "copy a fullscreen screenshot",
        "color_picker": "pick a color with Hyprpicker",
        "zoom_out": "decrease scrolling column size by 0.3",
        "zoom_in": "increase scrolling column size by 0.3",
        "move": "move the active window with the pointer",
        "resize": "resize the active window with the pointer",
        "enter": "enter Adjust mode",
        "exit": "leave Adjust mode",
        "reorder": "reorder the active window",
    }
    for section in SECTION_ORDER:
        for action in SECTION_ACTIONS.get(section, ()):
            description = descriptions.get(action, action)
            if section == "adjust" and action == "resize":
                description = "resize the active window by 40px"
            lines.append(f"| `{section}` | `{action}` | {description} |")
    lines.append("| `extra.exec` | `named command` | run an allowlisted process or shell command |")
    lines.extend(
        [
            "",
            "## Current bindings",
            "",
            "| Mode | Section | Action | Chord |",
            "| --- | --- | --- | --- |",
        ]
    )
    for binding in keymap.bindings:
        lines.append(f"| `{binding.mode}` | `{binding.section}` | `{binding.action}` | `{_display_chord(binding)}` |")
    for item in keymap.extra_exec:
        lines.append(f"| `{item.mode}` | `extra.exec` | `{item.name}` | `{item.chord.canonical}` |")
    lines.extend(
        [
            "",
            "## Adjust mode",
            "",
            "`adjust.enter` enters the finite Adjust mode. `adjust.exit` must include unmodified `Esc` and `Enter`; extra exit chords are allowed. "
            "`adjust.reorder` must contain exactly unmodified `h/j/k/l`; `adjust.resize` must contain exactly `Shift+h/j/k/l`. "
            "The reorder and resize bindings repeat.",
            "",
            "The generated mode mapping is fixed: hardware actions are `universal`; Noctalia `lock` and `session_menu` are `universal`; "
            "Adjust actions other than `enter` are in `adjust`; all other actions are in `normal`. `submap_universal` keeps a binding "
            "active in Adjust; hardware bindings additionally use `locked = true` and remain available while the session is locked. "
            "Duplicate chords are rejected, and a universal chord cannot also be local.",
            "",
            "Unknown keys in Adjust mode are consumed by a generated `catchall` binding and leave the mode active.",
            "",
            "## extra.exec",
            "",
            "Each named command uses this shape:",
            "",
            "```toml",
            "[extra.exec.reload_bar]",
            "chord = \"mod+r\"",
            "command = \"waybar\"",
            "mode = \"normal\"",
            "```",
            "",
            "The name must match `[A-Za-z_][A-Za-z0-9_-]*`; `chord` and `command` are required; `mode` is optional and is `normal` by default, "
            "or may be `universal`. Direct commands must be a single allowlisted process invocation; shell operators require `sh -c '...'`, whose processes must all be allowlisted. "
            "Command substitution, raw Lua, `hyprctl`, and arbitrary Hyprland dispatch/control commands are rejected. The current process "
            "allowlist is `brightnessctl`, `grim`, `hypridle`, `hyprlock`, `hyprpaper`, `hyprpicker`, `noctalia`, `noctalia-shell`, "
            "`notify-send`, `pamixer`, `playerctl`, `slurp`, `systemctl`, `true`, `waybar`, and `wl-copy`.",
            "",
            "## Common special keys",
            "",
            "| Input spelling | Compiled spelling |",
            "| --- | --- |",
            "| `Esc`, `Enter`, `Space`, `Tab`, `Backspace`, `Print` | `Escape`, `Return`, `SPACE`, `Tab`, `BackSpace`, `Print` |",
            "| `-`, `=`, `[`, `]`, `,`, `.`, `/` | `minus`, `equal`, `bracketleft`, `bracketright`, `comma`, `period`, `slash` |",
            "| `mouse:left`, `mouse:right` | `mouse:272`, `mouse:273` |",
            "| `XF86AudioRaiseVolume` | unchanged |",
            "| `F1`-`F12` | valid spare keys; intentionally unbound |",
            "",
            "Pointer bindings use the Hyprland mouse option and button numbers. XF86 hardware keys "
            "are universal bindings and remain available while the session is locked and in Adjust mode. No workspace is fixed "
            "to a monitor; numbered workspaces remain global.",
            "",
        ]
    )
    return "\n".join(lines)


def list_keymap(path: Path = KEYMAP_PATH) -> str:
    keymap = load_keymap(path)
    lines = ["Supported actions:"]
    for section in SECTION_ORDER:
        for action in SECTION_ACTIONS.get(section, ()):
            lines.append(f"  {section}.{action}")
    lines.append("\nOccupied chords:")
    for binding in keymap.bindings:
        lines.append(f"  {binding.mode:9} {binding.chord.canonical:28} {binding.section}.{binding.action}")
    for item in keymap.extra_exec:
        lines.append(f"  {item.mode:9} {item.chord.canonical:28} extra.exec.{item.name}")
    lines.append("\nF1-F12 are legal spare keys and currently unbound.")
    return "\n".join(lines)
