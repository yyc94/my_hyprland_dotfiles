#!/usr/bin/env python3
"""Build and safely deploy the TOML-driven Hyprland configuration set."""

from __future__ import annotations

import argparse
import ast
import base64
import binascii
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import keymap


CONFIG_DIR = ROOT / "config"
DOC_DIR = ROOT / "doc"
CONFIG_ROOT_ENV = "HYPRLAND_CONFIG_ROOT"
GENERATED_DIR_REL = Path("config") / "generated"
AGGREGATE_REL = Path("config") / "generated.lua"
MANIFEST_REL = Path("config") / ".generated-manifest.json"
HISTORY_REL = Path("config") / ".generated-history.json"

PROFILE = "CachyOS Hypr/Noctalia"
TARGET_HYPRLAND = ">=0.55.0"
SCHEMA = "1"

SOURCE_FILES = {
    "variables": CONFIG_DIR / "variables.toml",
    "monitors": CONFIG_DIR / "monitors.toml",
    "workspaces": CONFIG_DIR / "workspaces.toml",
    "input": CONFIG_DIR / "input.toml",
    "rules": CONFIG_DIR / "rules.toml",
    "environment": CONFIG_DIR / "environment.toml",
    "autostart": CONFIG_DIR / "autostart.toml",
}

MODULE_REL = {
    "variables": GENERATED_DIR_REL / "variables.lua",
    "monitors": GENERATED_DIR_REL / "monitors.lua",
    "workspaces": GENERATED_DIR_REL / "workspaces.lua",
    "input": GENERATED_DIR_REL / "input.lua",
    "rules": GENERATED_DIR_REL / "rules.lua",
    "environment": GENERATED_DIR_REL / "environment.lua",
    "autostart": GENERATED_DIR_REL / "autostart.lua",
    "keymap": GENERATED_DIR_REL / "binds.lua",
}

DOMAIN_ORDER = (
    "variables",
    "monitors",
    "workspaces",
    "input",
    "rules",
    "environment",
    "autostart",
    "keymap",
)

COMMAND_NAMES = (
    "terminal",
    "file_manager",
    "browser",
    "calculator",
    "system_monitor",
)

MONITOR_TRANSFORMS = {
    "normal": 0,
    "90": 1,
    "180": 2,
    "270": 3,
    "flipped": 4,
    "flipped-90": 5,
    "flipped-180": 6,
    "flipped-270": 7,
}
MONITOR_VRR = {"off": 0, "on": 1, "fullscreen": 2}
FOLLOW_MOUSE = {"disabled": 0, "follow": 1, "detached": 2, "separate": 3}
FOCUS_ON_CLOSE = {"next": 0, "cursor": 1, "mru": 2}
ACCEL_PROFILES = {"adaptive", "flat", "custom"}
SCROLL_METHODS = {"2fg", "edge", "on_button_down", "no_scroll"}
OFF_WINDOW_AXIS_EVENTS = {"ignore": 0, "send": 1, "clamp": 2, "warp": 3}
EMULATE_DISCRETE_SCROLL = {"disable": 0, "non_standard": 1, "force_all": 2}

MATCH_STRING_FIELDS = {
    "class",
    "title",
    "initial_class",
    "initial_title",
    "tag",
    "workspace",
    "content",
    "xdg_tag",
    "namespace",
}
MATCH_BOOL_FIELDS = {
    "float",
    "xwayland",
    "fullscreen",
    "pin",
    "focus",
    "group",
    "modal",
}
MATCH_INT_FIELDS = {"fullscreen_state_internal", "fullscreen_state_client"}
WINDOW_MATCH_FIELDS = MATCH_STRING_FIELDS | MATCH_BOOL_FIELDS | MATCH_INT_FIELDS
LAYER_MATCH_FIELDS = {"namespace"}

WINDOW_BOOL_EFFECTS = {
    "float",
    "tile",
    "fullscreen",
    "maximize",
    "center",
    "pseudo",
    "no_initial_focus",
    "pin",
    "persistent_size",
    "allows_input",
    "dim_around",
    "decorate",
    "focus_on_activate",
    "keep_aspect_ratio",
    "nearest_neighbor",
    "no_anim",
    "no_blur",
    "no_dim",
    "no_focus",
    "no_follow_mouse",
    "no_max_size",
    "no_shadow",
    "no_shortcuts_inhibit",
    "opaque",
    "force_rgbx",
    "sync_fullscreen",
    "immediate",
    "xray",
    "render_unfocused",
    "no_screen_share",
    "no_vrr",
    "stay_focused",
    "confine_pointer",
}
WINDOW_STRING_EFFECTS = {
    "fullscreen_state",
    "monitor",
    "workspace",
    "group",
    "suppress_event",
    "content",
    "animation",
    "idle_inhibit",
    "opacity",
    "tag",
}
WINDOW_INT_EFFECTS = {"no_close_for", "rounding", "border_size"}
WINDOW_FLOAT_EFFECTS = {"scrolling_width", "rounding_power", "scroll_mouse", "scroll_touchpad"}
WINDOW_VECTOR_EFFECTS = {"move", "size", "max_size", "min_size"}
WINDOW_EFFECT_FIELDS = (
    WINDOW_BOOL_EFFECTS
    | WINDOW_STRING_EFFECTS
    | WINDOW_INT_EFFECTS
    | WINDOW_FLOAT_EFFECTS
    | WINDOW_VECTOR_EFFECTS
)
LAYER_BOOL_EFFECTS = {
    "no_anim",
    "blur",
    "blur_popups",
    "dim_around",
    "xray",
    "no_screen_share",
}
LAYER_STRING_EFFECTS = {"animation"}
LAYER_INT_EFFECTS = {"order", "above_lock"}
LAYER_FLOAT_EFFECTS = {"ignore_alpha"}
LAYER_EFFECT_FIELDS = LAYER_BOOL_EFFECTS | LAYER_STRING_EFFECTS | LAYER_INT_EFFECTS | LAYER_FLOAT_EFFECTS

ALLOWED_EXECUTABLES = {
    "brightnessctl",
    "grim",
    "hypridle",
    "hyprlock",
    "hyprpaper",
    "hyprpicker",
    "noctalia",
    "noctalia-shell",
    "notify-send",
    "pamixer",
    "playerctl",
    "slurp",
    "systemctl",
    "true",
    "waybar",
    "wl-copy",
}


class ConfigError(keymap.KeymapError):
    """Validation or deployment errors collected from one operation."""

    def __init__(self, errors: Iterable[str]):
        if isinstance(errors, str):
            errors = (errors,)
        self.errors = tuple(dict.fromkeys(errors))
        super().__init__(self.errors)


@dataclass(frozen=True)
class Source:
    name: str
    path: Path
    data: dict[str, Any]
    content_hash: str
    exists: bool


@dataclass(frozen=True)
class Build:
    keymap: keymap.Keymap
    sources: tuple[Source, ...]
    values: dict[str, Any]
    outputs: dict[Path, str]
    manifest: str
    config_doc: str


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib

        return tomllib.loads(path.read_text(encoding="utf-8"))
    except ModuleNotFoundError as exc:
        raise ConfigError(("Python 3.11+ is required because the compiler uses the standard-library tomllib",)) from exc
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError((f"{path}: invalid TOML ({exc})",)) from exc


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_source(name: str) -> Source:
    path = SOURCE_FILES[name]
    if not path.exists():
        return Source(name, path, {}, "missing", False)
    data = _read_toml(path)
    errors: list[str] = []
    if not isinstance(data, dict):
        errors.append(f"{path}: root must be a TOML table")
        data = {}
    _validate_meta(data, path, errors)
    if errors:
        raise ConfigError(errors)
    return Source(name, path, data, _hash_bytes(path.read_bytes()), True)


def _validate_meta(data: dict[str, Any], path: Path, errors: list[str]) -> None:
    meta = data.get("meta")
    if not isinstance(meta, dict):
        errors.append(f"{path}: meta: required table is missing")
        return
    allowed = {"schema", "target_hyprland", "profile"}
    for key in meta:
        if key not in allowed:
            errors.append(f"{path}: meta.{key}: unknown field")
    for key in allowed:
        if key not in meta:
            errors.append(f"{path}: meta.{key}: required field is missing")
    if meta.get("schema") not in {1, SCHEMA}:
        errors.append(f"{path}: meta.schema: must be 1 or \"1\"")
    if meta.get("target_hyprland") != TARGET_HYPRLAND:
        errors.append(f"{path}: meta.target_hyprland: must be {TARGET_HYPRLAND!r}")
    if not isinstance(meta.get("profile"), str) or not meta.get("profile", "").strip():
        errors.append(f"{path}: meta.profile: expected a non-empty string")


def _table(value: object, path: str, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{path}: expected a TOML table")
        return None
    return value


def _unknown(table: dict[str, Any], allowed: set[str], path: str, errors: list[str]) -> None:
    for key in table:
        if key not in allowed:
            errors.append(f"{path}.{key}: unknown field")


def _string(value: object, path: str, errors: list[str], *, nonempty: bool = True) -> str | None:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        errors.append(f"{path}: expected a {'non-empty ' if nonempty else ''}string")
        return None
    return value


def _optional_string(table: dict[str, Any], key: str, path: str, errors: list[str], *, nonempty: bool = True) -> str | None:
    if key not in table:
        return None
    return _string(table[key], f"{path}.{key}", errors, nonempty=nonempty)


def _optional_bool(table: dict[str, Any], key: str, path: str, errors: list[str]) -> bool | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, bool):
        errors.append(f"{path}.{key}: expected a boolean")
        return None
    return value


def _number(value: object, path: str, errors: list[str], *, minimum: float | None = None, maximum: float | None = None) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{path}: expected a number")
        return None
    if isinstance(value, float) and not math.isfinite(value):
        errors.append(f"{path}: must be a finite number")
        return None
    if minimum is not None and value < minimum:
        errors.append(f"{path}: must be >= {minimum}")
    if maximum is not None and value > maximum:
        errors.append(f"{path}: must be <= {maximum}")
    return value


def _integer(value: object, path: str, errors: list[str], *, minimum: int | None = None, maximum: int | None = None) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{path}: expected an integer")
        return None
    if minimum is not None and value < minimum:
        errors.append(f"{path}: must be >= {minimum}")
    if maximum is not None and value > maximum:
        errors.append(f"{path}: must be <= {maximum}")
    return value


def _parse_variables(source: Source, errors: list[str]) -> dict[str, Any]:
    data = source.data
    _unknown(data, {"meta", "commands"}, str(source.path), errors)
    commands_value = data.get("commands", {})
    commands = _table(commands_value, f"{source.path}: commands", errors)
    if commands is None:
        return {"commands": {}}
    result: dict[str, str] = {}
    for name, value in commands.items():
        path = f"{source.path}: commands.{name}"
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            errors.append(f"{path}: command name must be a Lua identifier")
            continue
        parsed = _string(value, path, errors)
        if parsed is not None:
            result[name] = parsed
    return {"commands": result}


def _parse_monitor_position(value: object, path: str, errors: list[str]) -> str | None:
    if isinstance(value, str):
        if value != "auto":
            errors.append(f"{path}: expected \"auto\" or a table with integer x and y")
            return None
        return value
    if not isinstance(value, dict):
        errors.append(f"{path}: expected \"auto\" or a table with integer x and y")
        return None
    if set(value) != {"x", "y"}:
        errors.append(f"{path}: expected exactly x and y")
        return None
    x = _integer(value.get("x"), f"{path}.x", errors)
    y = _integer(value.get("y"), f"{path}.y", errors)
    if x is None or y is None:
        return None
    return f"{x}x{y}"


def _parse_monitor(source: Source, errors: list[str]) -> list[dict[str, Any]]:
    data = source.data
    _unknown(data, {"meta", "monitor"}, str(source.path), errors)
    items = data.get("monitor", [])
    if not isinstance(items, list):
        errors.append(f"{source.path}: monitor: expected an array of tables")
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    allowed = {"output", "mode", "position", "scale", "disabled", "transform", "vrr"}
    for index, raw in enumerate(items):
        path = f"{source.path}: monitor[{index}]"
        item = _table(raw, path, errors)
        if item is None:
            continue
        _unknown(item, allowed, path, errors)
        output = _string(item.get("output"), f"{path}.output", errors)
        if output is None:
            continue
        if output in seen:
            errors.append(f"{path}.output: duplicate monitor output {output!r}")
        seen.add(output)
        parsed: dict[str, Any] = {"output": output}
        mode = _optional_string(item, "mode", path, errors)
        if mode is not None:
            parsed["mode"] = mode
        if "position" in item:
            position = _parse_monitor_position(item["position"], f"{path}.position", errors)
            if position is not None:
                parsed["position"] = position
        if "scale" in item:
            scale_value = item["scale"]
            if isinstance(scale_value, str):
                if scale_value != "auto":
                    errors.append(f"{path}.scale: expected \"auto\" or a number >= 0.25")
                else:
                    parsed["scale"] = scale_value
            else:
                scale = _number(scale_value, f"{path}.scale", errors, minimum=0.25)
                if scale is not None:
                    parsed["scale"] = str(scale)
        disabled = _optional_bool(item, "disabled", path, errors)
        if disabled is not None:
            parsed["disabled"] = disabled
        if "transform" in item:
            transform = item["transform"]
            if isinstance(transform, int) and not isinstance(transform, bool):
                transform = str(transform)
            if not isinstance(transform, str) or transform not in MONITOR_TRANSFORMS:
                errors.append(f"{path}.transform: expected one of {', '.join(MONITOR_TRANSFORMS)}")
            else:
                parsed["transform"] = MONITOR_TRANSFORMS[transform]
        if "vrr" in item:
            vrr = item["vrr"]
            if not isinstance(vrr, str) or vrr not in MONITOR_VRR:
                errors.append(f"{path}.vrr: expected one of {', '.join(MONITOR_VRR)}")
            else:
                parsed["vrr"] = MONITOR_VRR[vrr]
        result.append(parsed)
    return result


def _parse_workspaces(source: Source, errors: list[str]) -> list[dict[str, Any]]:
    data = source.data
    _unknown(data, {"meta", "workspace"}, str(source.path), errors)
    items = data.get("workspace", [])
    if not isinstance(items, list):
        errors.append(f"{source.path}: workspace: expected an array of tables")
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    allowed = {"workspace", "monitor", "default", "persistent", "layout"}
    for index, raw in enumerate(items):
        path = f"{source.path}: workspace[{index}]"
        item = _table(raw, path, errors)
        if item is None:
            continue
        _unknown(item, allowed, path, errors)
        selector = _string(item.get("workspace"), f"{path}.workspace", errors)
        if selector is None:
            continue
        if selector in seen:
            errors.append(f"{path}.workspace: duplicate workspace selector {selector!r}")
        seen.add(selector)
        parsed: dict[str, Any] = {"workspace": selector}
        monitor = _optional_string(item, "monitor", path, errors)
        if monitor is not None:
            parsed["monitor"] = monitor
        for field in ("default", "persistent"):
            value = _optional_bool(item, field, path, errors)
            if value is not None:
                parsed[field] = value
        layout = _optional_string(item, "layout", path, errors)
        if layout is not None:
            parsed["layout"] = layout
        result.append(parsed)
    return result


def _parse_input(source: Source, errors: list[str]) -> dict[str, dict[str, Any]]:
    data = source.data
    _unknown(data, {"meta", "keyboard", "mouse"}, str(source.path), errors)
    result: dict[str, dict[str, Any]] = {"keyboard": {}, "mouse": {}}
    keyboard = data.get("keyboard", {})
    mouse = data.get("mouse", {})
    keyboard_table = _table(keyboard, f"{source.path}: keyboard", errors)
    mouse_table = _table(mouse, f"{source.path}: mouse", errors)
    if keyboard_table is not None:
        allowed = {
            "layout",
            "variant",
            "model",
            "options",
            "rules",
            "repeat_rate",
            "repeat_delay",
            "numlock_by_default",
            "resolve_binds_by_sym",
        }
        _unknown(keyboard_table, allowed, f"{source.path}: keyboard", errors)
        mapping = {"layout": "kb_layout", "variant": "kb_variant", "model": "kb_model", "options": "kb_options", "rules": "kb_rules"}
        for source_key, lua_key in mapping.items():
            value = _optional_string(keyboard_table, source_key, f"{source.path}: keyboard", errors, nonempty=False)
            if value is not None:
                result["keyboard"][lua_key] = value
        for field, minimum, maximum in (("repeat_rate", 0, 200), ("repeat_delay", 0, 2000)):
            if field in keyboard_table:
                value = _integer(keyboard_table[field], f"{source.path}: keyboard.{field}", errors, minimum=minimum, maximum=maximum)
                if value is not None:
                    result["keyboard"][field] = value
        for field in ("numlock_by_default", "resolve_binds_by_sym"):
            value = _optional_bool(keyboard_table, field, f"{source.path}: keyboard", errors)
            if value is not None:
                result["keyboard"][field] = value
    if mouse_table is not None:
        allowed = {
            "follow",
            "follow_threshold",
            "focus_on_close",
            "mouse_refocus",
            "float_switch_override_focus",
            "sensitivity",
            "accel_profile",
            "force_no_accel",
            "rotation",
            "left_handed",
            "scroll_method",
            "scroll_button",
            "scroll_button_lock",
            "scroll_points",
            "scroll_factor",
            "natural_scroll",
            "special_fallthrough",
            "off_window_axis_events",
            "emulate_discrete_scroll",
            "follow_mouse_shrink",
        }
        _unknown(mouse_table, allowed, f"{source.path}: mouse", errors)
        enum_fields = {
            "follow": (FOLLOW_MOUSE, "follow_mouse"),
            "focus_on_close": (FOCUS_ON_CLOSE, "focus_on_close"),
            "accel_profile": ({name: name for name in ACCEL_PROFILES}, "accel_profile"),
            "scroll_method": ({name: name for name in SCROLL_METHODS}, "scroll_method"),
            "off_window_axis_events": (OFF_WINDOW_AXIS_EVENTS, "off_window_axis_events"),
            "emulate_discrete_scroll": (EMULATE_DISCRETE_SCROLL, "emulate_discrete_scroll"),
        }
        for field, (choices, lua_key) in enum_fields.items():
            if field not in mouse_table:
                continue
            value = mouse_table[field]
            if not isinstance(value, str) or value not in choices:
                errors.append(f"{source.path}: mouse.{field}: expected one of {', '.join(sorted(choices))}")
            else:
                result["mouse"][lua_key] = choices[value]
        for field in ("mouse_refocus", "force_no_accel", "left_handed", "scroll_button_lock", "natural_scroll", "special_fallthrough"):
            value = _optional_bool(mouse_table, field, f"{source.path}: mouse", errors)
            if value is not None:
                result["mouse"][field] = value
        for field, minimum, maximum in (
            ("follow_threshold", 0, None),
            ("sensitivity", -1, 1),
            ("scroll_factor", 0, 2),
        ):
            if field in mouse_table:
                value = _number(mouse_table[field], f"{source.path}: mouse.{field}", errors, minimum=minimum, maximum=maximum)
                if value is not None:
                    result["mouse"][field if field != "follow_threshold" else "follow_mouse_threshold"] = value
        if "float_switch_override_focus" in mouse_table:
            value = _integer(mouse_table["float_switch_override_focus"], f"{source.path}: mouse.float_switch_override_focus", errors, minimum=0, maximum=2)
            if value is not None:
                result["mouse"]["float_switch_override_focus"] = value
        if "rotation" in mouse_table:
            value = _integer(mouse_table["rotation"], f"{source.path}: mouse.rotation", errors, minimum=0, maximum=359)
            if value is not None:
                result["mouse"]["rotation"] = value
        if "scroll_button" in mouse_table:
            value = _integer(mouse_table["scroll_button"], f"{source.path}: mouse.scroll_button", errors, minimum=0, maximum=300)
            if value is not None:
                result["mouse"]["scroll_button"] = value
        if "scroll_points" in mouse_table:
            value = _string(mouse_table["scroll_points"], f"{source.path}: mouse.scroll_points", errors, nonempty=False)
            if value is not None:
                result["mouse"]["scroll_points"] = value
        if "follow_mouse_shrink" in mouse_table:
            value = _integer(mouse_table["follow_mouse_shrink"], f"{source.path}: mouse.follow_mouse_shrink", errors, minimum=0, maximum=300)
            if value is not None:
                result["mouse"]["follow_mouse_shrink"] = value
    return result


def _parse_rules(source: Source, errors: list[str]) -> dict[str, list[dict[str, Any]]]:
    data = source.data
    _unknown(data, {"meta", "windowrule", "layerrule"}, str(source.path), errors)
    result: dict[str, list[dict[str, Any]]] = {"windowrule": [], "layerrule": []}
    for kind, match_fields, effect_fields in (
        ("windowrule", WINDOW_MATCH_FIELDS, WINDOW_EFFECT_FIELDS),
        ("layerrule", LAYER_MATCH_FIELDS, LAYER_EFFECT_FIELDS),
    ):
        items = data.get(kind, [])
        if not isinstance(items, list):
            errors.append(f"{source.path}: {kind}: expected an array of tables")
            continue
        names: set[str] = set()
        for index, raw in enumerate(items):
            path = f"{source.path}: {kind}[{index}]"
            item = _table(raw, path, errors)
            if item is None:
                continue
            _unknown(item, {"name", "enabled", "match", "effects"}, path, errors)
            name = _string(item.get("name"), f"{path}.name", errors)
            if name is None:
                continue
            if name in names:
                errors.append(f"{path}.name: duplicate rule name {name!r}")
            names.add(name)
            match = _table(item.get("match"), f"{path}.match", errors)
            effects = _table(item.get("effects"), f"{path}.effects", errors)
            if match is None or not match:
                errors.append(f"{path}.match: at least one matcher is required")
                match = {}
            if effects is None or not effects:
                errors.append(f"{path}.effects: at least one effect is required")
                effects = {}
            _unknown(match, match_fields, f"{path}.match", errors)
            parsed_match: dict[str, Any] = {}
            for field, value in match.items():
                field_path = f"{path}.match.{field}"
                if field in MATCH_STRING_FIELDS:
                    parsed = _string(value, field_path, errors)
                elif field in MATCH_BOOL_FIELDS:
                    if not isinstance(value, bool):
                        errors.append(f"{field_path}: expected a boolean")
                        parsed = None
                    else:
                        parsed = value
                else:
                    parsed = _integer(value, field_path, errors)
                if parsed is not None:
                    parsed_match[field] = parsed
            _unknown(effects, effect_fields, f"{path}.effects", errors)
            parsed_effects: dict[str, Any] = {}
            for field, value in effects.items():
                field_path = f"{path}.effects.{field}"
                parsed: Any = None
                if field in WINDOW_BOOL_EFFECTS or field in LAYER_BOOL_EFFECTS:
                    if not isinstance(value, bool):
                        errors.append(f"{field_path}: expected a boolean")
                    else:
                        parsed = value
                elif field in WINDOW_STRING_EFFECTS or field in LAYER_STRING_EFFECTS:
                    parsed = _string(value, field_path, errors)
                elif field in WINDOW_INT_EFFECTS or field in LAYER_INT_EFFECTS:
                    minimum = 0 if field in {"rounding", "border_size", "above_lock"} else None
                    maximum = 20 if field == "rounding" else 2 if field == "above_lock" else None
                    parsed = _integer(value, field_path, errors, minimum=minimum, maximum=maximum)
                elif field in WINDOW_FLOAT_EFFECTS or field in LAYER_FLOAT_EFFECTS:
                    minimum = 0.01 if field in {"scroll_mouse", "scroll_touchpad"} else 0
                    maximum = 10 if field in {"scroll_mouse", "scroll_touchpad"} else 1 if field == "ignore_alpha" else None
                    parsed = _number(value, field_path, errors, minimum=minimum, maximum=maximum)
                elif field in WINDOW_VECTOR_EFFECTS:
                    if not isinstance(value, dict) or set(value) != {"x", "y"}:
                        errors.append(f"{field_path}: expected a table with x and y values")
                    else:
                        x = _number(value.get("x"), f"{field_path}.x", errors)
                        y = _number(value.get("y"), f"{field_path}.y", errors)
                        if x is not None and y is not None:
                            parsed = [x, y]
                if parsed is not None:
                    parsed_effects[field] = parsed
            enabled = _optional_bool(item, "enabled", path, errors)
            result[kind].append({"name": name, "enabled": True if enabled is None else enabled, "match": parsed_match, "effects": parsed_effects})
    return result


def _parse_environment(source: Source, errors: list[str]) -> dict[str, str]:
    data = source.data
    _unknown(data, {"meta", "environment"}, str(source.path), errors)
    table = _table(data.get("environment", {}), f"{source.path}: environment", errors)
    if table is None:
        return {}
    result: dict[str, str] = {}
    for name, value in table.items():
        path = f"{source.path}: environment.{name}"
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            errors.append(f"{path}: invalid environment variable name")
            continue
        parsed = _string(value, path, errors)
        if parsed is not None:
            result[name] = parsed
    return result


def _parse_autostart(source: Source, errors: list[str]) -> list[dict[str, Any]]:
    data = source.data
    _unknown(data, {"meta", "exec_once"}, str(source.path), errors)
    items = data.get("exec_once", [])
    if not isinstance(items, list):
        errors.append(f"{source.path}: exec_once: expected an array of tables")
        return []
    result: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, raw in enumerate(items):
        path = f"{source.path}: exec_once[{index}]"
        item = _table(raw, path, errors)
        if item is None:
            continue
        _unknown(item, {"name", "command"}, path, errors)
        name = _string(item.get("name"), f"{path}.name", errors)
        if name is None or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", name) is None:
            if name is not None:
                errors.append(f"{path}.name: command name must be a non-empty identifier")
            continue
        if name in names:
            errors.append(f"{path}.name: duplicate command name {name!r}")
        names.add(name)
        command = item.get("command")
        if not isinstance(command, list) or not command:
            errors.append(f"{path}.command: expected a non-empty argv array")
            continue
        argv: list[str] = []
        for arg_index, arg in enumerate(command):
            parsed = _string(arg, f"{path}.command[{arg_index}]", errors)
            if parsed is not None:
                argv.append(parsed)
        if not argv:
            continue
        executable = Path(argv[0]).name
        if executable not in ALLOWED_EXECUTABLES or "/" in argv[0]:
            errors.append(f"{path}.command[0]: executable {executable!r} is not in the controlled process allowlist")
        if any(any(token in arg for token in ("\x00", "$(", "`", ";", "&&", "||", "|", ">", "<")) for arg in argv):
            errors.append(f"{path}.command: shell operators and command substitution are not allowed")
        result.append({"name": name, "command": argv})
    return result


def _lua_key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) else f"[{json.dumps(key, ensure_ascii=True)}]"


def _lua_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, list):
        return "{ " + ", ".join(_lua_value(item) for item in value) + " }"
    if isinstance(value, dict):
        return _lua_table(value)
    raise TypeError(f"unsupported Lua value {value!r}")


def _lua_table(value: dict[str, Any], indent: int = 0) -> str:
    if not value:
        return "{}"
    prefix = "\t" * indent
    child = "\t" * (indent + 1)
    lines = ["{"]
    for key, item in value.items():
        rendered = _lua_value(item)
        if "\n" in rendered:
            rendered = rendered.replace("\n", "\n" + child)
        lines.append(f"{child}{_lua_key(key)} = {rendered},")
    lines.append(f"{prefix}}}")
    return "\n".join(lines)


def _module_header(source: str, content_hash: str) -> list[str]:
    return [
        "-- GENERATED FILE. DO NOT EDIT.",
        f"-- Source: {source}",
        f"-- Content-SHA256: {content_hash}",
        f"-- Target: Hyprland {TARGET_HYPRLAND}, {PROFILE} profile",
        "",
    ]


def _render_variables(values: dict[str, Any], source: Source) -> str:
    body = "return " + _lua_table({"commands": values["commands"]})
    return "\n".join(_module_header("config/variables.toml", source.content_hash) + [body, ""])


def _render_monitors(values: list[dict[str, Any]], source: Source) -> str:
    lines = _module_header("config/monitors.toml", source.content_hash)
    if not values:
        lines.append("-- No monitor rules are configured.")
    for item in values:
        lines.extend([f"hl.monitor({_lua_table(item)})", ""])
    return "\n".join(lines).rstrip() + "\n"


def _render_workspaces(values: list[dict[str, Any]], source: Source) -> str:
    lines = _module_header("config/workspaces.toml", source.content_hash)
    if not values:
        lines.append("-- No workspace rules are configured.")
    for item in values:
        lines.extend([f"hl.workspace_rule({_lua_table(item)})", ""])
    return "\n".join(lines).rstrip() + "\n"


def _render_input(values: dict[str, dict[str, Any]], source: Source) -> str:
    input_table: dict[str, Any] = {}
    input_table.update(values["keyboard"])
    input_table.update(values["mouse"])
    lines = _module_header("config/input.toml", source.content_hash)
    if not input_table:
        lines.append("-- No global input settings are configured.")
    else:
        lines.extend(["hl.config({", "\tinput = " + _lua_table(input_table, 1), "})", ""])
    return "\n".join(lines).rstrip() + "\n"


def _render_rules(values: dict[str, list[dict[str, Any]]], source: Source) -> str:
    lines = _module_header("config/rules.toml", source.content_hash)
    if not values["windowrule"] and not values["layerrule"]:
        lines.append("-- No window or layer rules are configured.")
    for kind, api_name in (("windowrule", "window_rule"), ("layerrule", "layer_rule")):
        for item in values[kind]:
            table: dict[str, Any] = {"name": item["name"], "enabled": item["enabled"], "match": item["match"]}
            table.update(item["effects"])
            lines.extend([f"hl.{api_name}({_lua_table(table)})", ""])
    return "\n".join(lines).rstrip() + "\n"


def _render_environment(values: dict[str, str], source: Source) -> str:
    lines = _module_header("config/environment.toml", source.content_hash)
    if not values:
        lines.append("-- No environment variables are configured.")
    for name in sorted(values):
        lines.extend([f"hl.env({_lua_value(name)}, {_lua_value(values[name])})", ""])
    return "\n".join(lines).rstrip() + "\n"


def _render_autostart(values: list[dict[str, Any]], source: Source) -> str:
    lines = _module_header("config/autostart.toml", source.content_hash)
    if not values:
        lines.append("-- No one-shot startup commands are configured.")
    for item in values:
        command = shlex.join(item["command"])
        lines.extend(
            [
                "-- exec_once",
                'hl.on("hyprland.start", function()',
                f"\thl.exec_cmd({_lua_value(command)})",
                "end)",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_aggregate(sources: Iterable[Source]) -> str:
    hashes = [f"{source.path.relative_to(ROOT)}={source.content_hash}" for source in sources]
    lines = _module_header("config/*.toml", _hash_bytes("\n".join(hashes).encode("utf-8")))
    lines.extend(
        [
            "-- Keep Hyprland autoreload disabled; just apply and just rollback reload explicitly.",
            "hl.config({ misc = { disable_autoreload = true } })",
            "",
        ]
    )
    for name in DOMAIN_ORDER:
        lines.extend([f'require("config.generated.{"binds" if name == "keymap" else name}")', ""])
    return "\n".join(lines).rstrip() + "\n"


def _render_config_doc(sources: tuple[Source, ...]) -> str:
    source_digest = _hash_bytes("\n".join(source.content_hash for source in sources).encode("utf-8"))
    lines = [
        "<!-- GENERATED FILE. DO NOT EDIT. -->",
        "<!-- Sources: config/*.toml and the schema registry -->",
        f"<!-- Content-SHA256: {source_digest} -->",
        "",
        "# TOML Configuration",
        "",
        "This document is generated from the registered TOML schemas. Generated Lua is deployed under `$HYPRLAND_CONFIG_ROOT/config/generated/`.",
        "Unlisted fields are intentionally unsupported and belong in `config/manual.lua`.",
        "",
        "## Common metadata",
        "",
        "Every domain file uses `[meta]` with `schema = \"1\"`, `target_hyprland = \">=0.55.0\"`, and a non-empty `profile`.",
        "Missing source files produce empty generated modules; they do not add defaults.",
        "",
        "## Domains",
        "",
        "| Source | TOML tables | Generated API |",
        "| --- | --- | --- |",
        "| `variables.toml` | `[commands]` | returns command data for keymap |",
        "| `monitors.toml` | `[[monitor]]` | `hl.monitor` |",
        "| `workspaces.toml` | `[[workspace]]` | `hl.workspace_rule` |",
        "| `input.toml` | `[keyboard]`, `[mouse]` | `hl.config({ input = ... })` |",
        "| `rules.toml` | `[[windowrule]]`, `[[layerrule]]` | `hl.window_rule`, `hl.layer_rule` |",
        "| `environment.toml` | `[environment]` | `hl.env` |",
        "| `autostart.toml` | `[[exec_once]]` | `hl.on(\"hyprland.start\")` and `hl.exec_cmd` |",
        "",
        "## Field registry",
        "",
        "### monitors.toml",
        "",
        "`output` is required. Optional fields: `mode`, `position` (`\"auto\"` or `{ x, y }`), `scale` (`\"auto\"` or a number >= 0.25), `disabled`, `transform` (`normal`, `90`, `180`, `270`, and flipped variants), and `vrr` (`off`, `on`, `fullscreen`).",
        "",
        "### workspaces.toml",
        "",
        "`workspace` is required. Optional fields: `monitor`, `default`, `persistent`, and `layout`.",
        "",
        "### input.toml",
        "",
        "Keyboard fields: `layout`, `variant`, `model`, `options`, `rules`, `repeat_rate`, `repeat_delay`, `numlock_by_default`, `resolve_binds_by_sym`.",
        "",
        "Mouse fields: `follow`, `follow_threshold`, `focus_on_close`, `mouse_refocus`, `float_switch_override_focus`, `sensitivity`, `accel_profile`, `force_no_accel`, `rotation`, `left_handed`, `scroll_method`, `scroll_button`, `scroll_button_lock`, `scroll_points`, `scroll_factor`, `natural_scroll`, `special_fallthrough`, `off_window_axis_events`, `emulate_discrete_scroll`, `follow_mouse_shrink`.",
        "",
        "Touchpad, device-specific settings, and gestures are not in this schema.",
        "",
        "### rules.toml",
        "",
        f"Window matchers: `{', '.join(sorted(WINDOW_MATCH_FIELDS))}`.",
        f"Layer matchers: `{', '.join(sorted(LAYER_MATCH_FIELDS))}`.",
        "Rules require unique names, at least one matcher, and at least one effect. Matcher strings are interpreted by Hyprland; the compiler does not implement regex semantics.",
        "",
        f"Window effects: `{', '.join(sorted(WINDOW_EFFECT_FIELDS))}`.",
        f"Layer effects: `{', '.join(sorted(LAYER_EFFECT_FIELDS))}`.",
        "",
        "### environment.toml",
        "",
        "`[environment]` contains non-empty environment names and string values. Values are literal: there is no shell expansion, command substitution, or implicit import from the current shell.",
        "",
        "### autostart.toml",
        "",
        "Each `exec_once` entry has a unique `name` and a non-empty `command` argv array. The executable must be in the compiler allowlist; shell operators and command substitution are rejected.",
        "",
        "## Escape hatch",
        "",
        "Use the hand-maintained `config/manual.lua` for unsupported Hyprland APIs, complex shell logic, permissions, device settings, gestures, plugins, or Noctalia configuration. It is loaded before `config.generated`; the compiler only checks its Lua syntax.",
        "",
    ]
    return "\n".join(lines)


def _build() -> Build:
    errors: list[str] = []
    try:
        loaded_keymap = keymap.load_keymap()
    except keymap.KeymapError as exc:
        errors.extend(exc.errors)
        loaded_keymap = None
    loaded: dict[str, Source] = {}
    values: dict[str, Any] = {}
    parsers = {
        "variables": _parse_variables,
        "monitors": _parse_monitor,
        "workspaces": _parse_workspaces,
        "input": _parse_input,
        "rules": _parse_rules,
        "environment": _parse_environment,
        "autostart": _parse_autostart,
    }
    for name in SOURCE_FILES:
        try:
            source = _load_source(name)
        except ConfigError as exc:
            errors.extend(exc.errors)
            continue
        loaded[name] = source
        values[name] = parsers[name](source, errors)
    if loaded_keymap is not None:
        commands = values.get("variables", {}).get("commands", {})
        application = loaded_keymap.data.get("application", {})
        if isinstance(application, dict):
            for action in COMMAND_NAMES:
                if action in application and action not in commands:
                    errors.append(f"application.{action}: missing variables.commands.{action} in config/variables.toml")
    if errors or loaded_keymap is None:
        raise ConfigError(errors or ("keymap: unable to build configuration",))
    sources = tuple(loaded[name] for name in SOURCE_FILES)
    keymap_source = Source("keymap", keymap.KEYMAP_PATH, {}, loaded_keymap.source_hash, True)
    outputs: dict[Path, str] = {
        MODULE_REL["variables"]: _render_variables(values["variables"], loaded["variables"]),
        MODULE_REL["monitors"]: _render_monitors(values["monitors"], loaded["monitors"]),
        MODULE_REL["workspaces"]: _render_workspaces(values["workspaces"], loaded["workspaces"]),
        MODULE_REL["input"]: _render_input(values["input"], loaded["input"]),
        MODULE_REL["rules"]: _render_rules(values["rules"], loaded["rules"]),
        MODULE_REL["environment"]: _render_environment(values["environment"], loaded["environment"]),
        MODULE_REL["autostart"]: _render_autostart(values["autostart"], loaded["autostart"]),
        MODULE_REL["keymap"]: keymap.render_lua(loaded_keymap),
    }
    all_sources = (*sources, keymap_source)
    outputs[AGGREGATE_REL] = _render_aggregate(all_sources)
    manifest = _render_manifest(all_sources, outputs)
    return Build(loaded_keymap, sources, values, outputs, manifest, _render_config_doc(sources))


def _render_manifest(sources: tuple[Source, ...], outputs: dict[Path, str]) -> str:
    payload = {
        "format": 1,
        "generated": True,
        "files": [
            {"path": str(path), "sha256": _hash_bytes(content.encode("utf-8"))}
            for path, content in sorted(outputs.items(), key=lambda item: str(item[0]))
        ],
        "sources": {str(source.path.relative_to(ROOT)): source.content_hash for source in sources},
    }
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def _target_root() -> Path:
    value = os.environ.get(CONFIG_ROOT_ENV)
    if not value or not value.strip():
        raise ConfigError((f'{CONFIG_ROOT_ENV} is not set; define it once, for example `export {CONFIG_ROOT_ENV}="$HOME/.config/hypr"`',))
    return Path(value).expanduser().resolve()


def _target_path(root: Path, relative: Path) -> Path:
    return root / relative


def _manifest_path(root: Path) -> Path:
    return _target_path(root, MANIFEST_REL)


def _history_path(root: Path) -> Path:
    return _target_path(root, HISTORY_REL)


def _allowed_managed_path(relative: str) -> bool:
    path = Path(relative)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        return False
    return path == AGGREGATE_REL or relative.startswith(str(GENERATED_DIR_REL) + "/")


def _known_managed_paths() -> set[Path]:
    return {AGGREGATE_REL, *MODULE_REL.values()}


def _validate_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _is_known_managed_path(value: object) -> bool:
    if not isinstance(value, str):
        return False
    path = Path(value)
    return str(path) == value and _allowed_managed_path(value) and path in _known_managed_paths()


def _validate_manifest_payload(payload: object, path: Path) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("format") != 1 or payload.get("generated") is not True:
        raise ConfigError((f"{path}: unsupported or untrusted generated manifest",))
    files = payload.get("files")
    if not isinstance(files, list):
        raise ConfigError((f"{path}: files must be an array",))
    seen: set[Path] = set()
    for entry in files:
        relative = entry.get("path") if isinstance(entry, dict) else None
        if (
            not isinstance(entry, dict)
            or not _is_known_managed_path(relative)
            or Path(relative) in seen
            or not _validate_sha256(entry.get("sha256"))
        ):
            raise ConfigError((f"{path}: contains an unmanaged or invalid file entry",))
        seen.add(Path(relative))
    if seen != _known_managed_paths():
        raise ConfigError((f"{path}: generated file list is incomplete",))
    sources = payload.get("sources")
    known_sources = {str(source.relative_to(ROOT)) for source in SOURCE_FILES.values()} | {"config/keymap.toml"}
    if not isinstance(sources, dict) or any(
        not isinstance(name, str)
        or name not in known_sources
        or (value != "missing" and not _validate_sha256(value))
        for name, value in sources.items()
    ):
        raise ConfigError((f"{path}: contains an invalid source hash map",))
    return payload


def _valid_mode(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 0o777


def _validate_snapshot_entries(entries: object, path: Path) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        raise ConfigError((f"{path}: files must be an array",))
    seen: set[Path] = set()
    for entry in entries:
        relative = entry.get("path") if isinstance(entry, dict) else None
        content = entry.get("content") if isinstance(entry, dict) else None
        if (
            not isinstance(entry, dict)
            or not _is_known_managed_path(relative)
            or Path(relative) in seen
            or not _valid_mode(entry.get("mode"))
            or (content is not None and not isinstance(content, str))
        ):
            raise ConfigError((f"{path}: contains an invalid managed file snapshot",))
        if content is not None:
            try:
                base64.b64decode(content, validate=True)
            except (binascii.Error, ValueError, TypeError) as exc:
                raise ConfigError((f"{path}: contains invalid base64 for {relative}",)) from exc
        seen.add(Path(relative))
    if seen != _known_managed_paths():
        raise ConfigError((f"{path}: managed file snapshot is incomplete",))
    return entries


def _load_manifest(root: Path) -> dict[str, Any] | None:
    path = _manifest_path(root)
    if path.is_symlink():
        raise ConfigError((f"{path}: external symlinks are not managed",))
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError((f"{path}: invalid generated manifest ({exc})",)) from exc
    return _validate_manifest_payload(payload, path)


def _manifest_files(manifest: dict[str, Any] | None) -> set[Path]:
    if not manifest:
        return set()
    return {Path(entry["path"]) for entry in manifest["files"]}


def _guard_path(path: Path, relative: Path, managed: set[Path]) -> None:
    if path.is_symlink():
        raise ConfigError((f"{path}: refusing to manage a symlink",))
    if path.exists() and not path.is_file():
        raise ConfigError((f"{path}: expected a regular file",))
    if path.exists() and relative not in managed:
        raise ConfigError((f"{path}: exists but is not owned by the generated manifest",))


def _guard_paths(root: Path, paths: Iterable[Path], managed: set[Path]) -> None:
    config = root / "config"
    generated = root / GENERATED_DIR_REL
    if root.exists() and not root.is_dir():
        raise ConfigError((f"{root}: expected a directory",))
    if config.is_symlink() or generated.is_symlink():
        raise ConfigError((f"{generated}: refusing to operate through a symlinked generated directory",))
    if config.exists() and not config.is_dir():
        raise ConfigError((f"{config}: expected a directory",))
    if generated.exists() and not generated.is_dir():
        raise ConfigError((f"{generated}: expected a directory",))
    for relative in paths:
        _guard_path(_target_path(root, relative), relative, managed)
    manifest = _manifest_path(root)
    for metadata in (manifest, _history_path(root)):
        if metadata.is_symlink():
            raise ConfigError((f"{metadata}: refusing to manage a symlink",))
        if metadata.exists() and not metadata.is_file():
            raise ConfigError((f"{metadata}: expected a regular file",))


def _atomic_write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    old_mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    old_mode |= 0o200
    payload = content.encode("utf-8") if isinstance(content, str) else content
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    try:
        os.chmod(temporary, old_mode or 0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _remove(path: Path) -> None:
    if path.is_symlink():
        raise ConfigError((f"{path}: refusing to remove a symlink",))
    path.unlink(missing_ok=True)


def _snapshot(root: Path, paths: Iterable[Path]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for relative in sorted(set(paths), key=str):
        path = _target_path(root, relative)
        if path.is_symlink():
            raise ConfigError((f"{path}: refusing to snapshot a symlink",))
        if path.exists():
            result.append(
                {
                    "path": str(relative),
                    "content": base64.b64encode(path.read_bytes()).decode("ascii"),
                    "mode": stat.S_IMODE(path.stat().st_mode),
                }
            )
        else:
            result.append({"path": str(relative), "content": None, "mode": 0o644})
    return result


def _restore_snapshot(root: Path, snapshot: list[dict[str, Any]]) -> None:
    for entry in snapshot:
        relative = Path(entry["path"])
        if not _is_known_managed_path(str(relative)):
            raise ConfigError((f"snapshot contains unmanaged path {relative}",))
        path = _target_path(root, relative)
        if entry["content"] is None:
            _remove(path)
            continue
        try:
            payload = base64.b64decode(entry["content"], validate=True)
        except (binascii.Error, ValueError, TypeError) as exc:
            raise ConfigError((f"snapshot contains invalid base64 for {relative}",)) from exc
        _atomic_write(path, payload)
        os.chmod(path, entry["mode"])


def _guard_local_files(paths: Iterable[Path]) -> None:
    for path in paths:
        if path.is_symlink():
            raise ConfigError((f"{path}: refusing to manage a symlink",))
        if path.exists() and not path.is_file():
            raise ConfigError((f"{path}: expected a regular file",))


def _snapshot_local_files(paths: Iterable[Path]) -> dict[Path, tuple[bytes | None, int]]:
    paths = tuple(paths)
    _guard_local_files(paths)
    result: dict[Path, tuple[bytes | None, int]] = {}
    for path in paths:
        if path.exists():
            result[path] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        else:
            result[path] = (None, 0o644)
    return result


def _restore_local_files(snapshot: dict[Path, tuple[bytes | None, int]]) -> None:
    _guard_local_files(snapshot)
    for path, (content, mode) in snapshot.items():
        if content is None:
            _remove(path)
        else:
            _atomic_write(path, content)
            os.chmod(path, mode)


def _write_manifest(root: Path, content: str | None) -> None:
    path = _manifest_path(root)
    if content is None:
        _remove(path)
    else:
        _atomic_write(path, content)


def _write_outputs(root: Path, build: Build, old_manifest: dict[str, Any] | None) -> None:
    current_paths = set(build.outputs)
    old_paths = _manifest_files(old_manifest)
    managed = old_paths | current_paths
    _guard_paths(root, managed, old_paths)
    # Write dependencies before the aggregate entrypoint so an enabled Hyprland
    # watcher never sees a new entrypoint whose required modules are missing.
    output_items = sorted(build.outputs.items(), key=lambda item: (item[0] == AGGREGATE_REL, str(item[0])))
    for relative, content in output_items:
        _atomic_write(_target_path(root, relative), content)
    for relative in sorted(old_paths - current_paths, key=str):
        _remove(_target_path(root, relative))
    _write_manifest(root, build.manifest)


def _restore_target_state(
    root: Path,
    snapshot: list[dict[str, Any]],
    manifest_bytes: bytes | None,
    history_bytes: bytes | None = None,
) -> None:
    failures: list[str] = []
    try:
        _restore_snapshot(root, snapshot)
    except Exception as exc:
        failures.append(f"generated files: {exc}")
    try:
        _write_manifest(root, manifest_bytes)
    except Exception as exc:
        failures.append(f"manifest: {exc}")
    if history_bytes is not None or _history_path(root).exists():
        try:
            if history_bytes is None:
                _remove(_history_path(root))
            else:
                _atomic_write(_history_path(root), history_bytes)
        except Exception as exc:
            failures.append(f"rollback history: {exc}")
    if failures:
        raise ConfigError(tuple(failures))


def _check_docs(build: Build) -> list[str]:
    mismatches: list[str] = []
    expected = {DOC_DIR / "KEYMAP.md": keymap.render_doc(build.keymap), DOC_DIR / "CONFIG.md": build.config_doc}
    for path, content in expected.items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            mismatches.append(str(path))
    return mismatches


def generate(*, check_only: bool = False) -> list[str]:
    root = _target_root()
    build = _build()
    if not check_only and root == ROOT:
        raise ConfigError(("repository is the live Hyprland config root; use `just apply` for a controlled reload",))
    old_manifest = _load_manifest(root)
    paths = set(build.outputs) | _manifest_files(old_manifest)
    _guard_paths(root, paths, _manifest_files(old_manifest))
    doc_paths = (DOC_DIR / "KEYMAP.md", DOC_DIR / "CONFIG.md")
    _guard_local_files(doc_paths)
    mismatches: list[str] = []
    for relative, content in build.outputs.items():
        path = _target_path(root, relative)
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            mismatches.append(str(path))
    if old_manifest is None or _manifest_path(root).read_text(encoding="utf-8") != build.manifest:
        mismatches.append(str(_manifest_path(root)))
    mismatches.extend(_check_docs(build))
    if check_only:
        return list(dict.fromkeys(mismatches))
    snapshot = _snapshot(root, paths)
    doc_snapshot = _snapshot_local_files(doc_paths)
    old_manifest_bytes = _manifest_path(root).read_bytes() if _manifest_path(root).exists() else None
    try:
        _write_outputs(root, build, old_manifest)
        for path, content in ((DOC_DIR / "KEYMAP.md", keymap.render_doc(build.keymap)), (DOC_DIR / "CONFIG.md", build.config_doc)):
            _atomic_write(path, content)
    except Exception as exc:
        failures: list[str] = []
        try:
            _restore_snapshot(root, snapshot)
        except Exception as restore_exc:
            failures.append(f"generated files: {restore_exc}")
        try:
            _write_manifest(root, old_manifest_bytes)
        except Exception as restore_exc:
            failures.append(f"manifest: {restore_exc}")
        try:
            _restore_local_files(doc_snapshot)
        except Exception as restore_exc:
            failures.append(f"documentation: {restore_exc}")
        if failures:
            raise ConfigError((f"generation failed: {exc}", f"generation rollback failed: {'; '.join(failures)}")) from exc
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError((f"generation failed: {exc}; previous files were restored",)) from exc
    return []


def _lua_binary() -> str | None:
    return os.environ.get("LUA") or shutil.which("lua5.5")


def _lua_syntax_check(path: Path) -> None:
    lua = _lua_binary()
    if lua is None:
        print(f"warning: no external Lua interpreter; skipped syntax check for {path}", file=sys.stderr)
        return
    expression = f"assert(loadfile({json.dumps(str(path), ensure_ascii=True)}))"
    try:
        result = subprocess.run([lua, "-e", expression], capture_output=True, text=True)
    except OSError as exc:
        raise ConfigError((f"Lua syntax checker could not be executed: {exc}",)) from exc
    if result.returncode:
        raise ConfigError((f"{path}: Lua syntax check failed: {result.stderr.strip() or result.stdout.strip()}",))


def _syntax_check_outputs(build: Build) -> None:
    with tempfile.TemporaryDirectory(prefix="hyprland-generated-") as directory:
        temp_root = Path(directory)
        for relative, content in build.outputs.items():
            path = temp_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            _lua_syntax_check(path)


def _hyprctl_command() -> str:
    return os.environ.get("HYPRCTL", "hyprctl")


def _run_hyprctl(*arguments: str) -> subprocess.CompletedProcess[str]:
    command = _hyprctl_command()
    try:
        return subprocess.run([command, *arguments], capture_output=True, text=True)
    except OSError as exc:
        return subprocess.CompletedProcess([command, *arguments], 127, "", str(exc))


def _config_errors() -> list[Any]:
    result = _run_hyprctl("-j", "configerrors")
    if result.returncode:
        raise ConfigError((f"hyprctl -j configerrors failed: {result.stderr.strip() or result.stdout.strip()}",))
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise ConfigError((f"hyprctl -j configerrors returned invalid JSON: {exc}",)) from exc
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        errors = payload.get("errors", [])
        return errors if isinstance(errors, list) else [errors]
    return [payload]


def _reload() -> tuple[bool, str]:
    result = _run_hyprctl("reload")
    if result.returncode:
        return False, result.stderr.strip() or result.stdout.strip() or "hyprctl reload failed"
    try:
        errors = _config_errors()
    except ConfigError as exc:
        return False, str(exc)
    if errors:
        return False, json.dumps(errors, ensure_ascii=True)
    return True, ""


def _write_history(root: Path, manifest: dict[str, Any] | None, snapshot: list[dict[str, Any]]) -> None:
    path = _history_path(root)
    if path.is_symlink():
        raise ConfigError((f"{path}: refusing to manage a symlink",))
    if path.exists() and not path.is_file():
        raise ConfigError((f"{path}: expected a regular file",))
    payload = {"format": 1, "manifest": manifest, "files": snapshot}
    _atomic_write(path, json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n")


def _read_history(root: Path) -> dict[str, Any]:
    path = _history_path(root)
    if path.is_symlink():
        raise ConfigError((f"{path}: external symlinks are not managed",))
    if not path.exists():
        raise ConfigError(("no applied configuration rollback history exists",))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError((f"{path}: invalid rollback history ({exc})",)) from exc
    if not isinstance(payload, dict) or payload.get("format") != 1:
        raise ConfigError((f"{path}: unsupported rollback history",))
    _validate_snapshot_entries(payload.get("files"), path)
    manifest = payload.get("manifest")
    if manifest is not None:
        try:
            _validate_manifest_payload(manifest, path)
        except ConfigError as exc:
            raise ConfigError((f"{path}: contains an invalid previous manifest: {exc}",)) from exc
    return payload


def apply() -> None:
    root = _target_root()
    build = _build()
    old_manifest = _load_manifest(root)
    old_paths = _manifest_files(old_manifest)
    candidate_paths = set(build.outputs)
    managed = old_paths | candidate_paths
    _guard_paths(root, managed, old_paths)
    for path in (ROOT / "hyprland.lua", ROOT / "config" / "manual.lua"):
        if not path.is_file():
            raise ConfigError((f"{path}: hand-maintained source is missing",))
        _lua_syntax_check(path)
    _syntax_check_outputs(build)
    baseline = _config_errors()
    if baseline:
        raise ConfigError(("existing Hyprland configuration errors:\n" + "\n".join(map(str, baseline)),))
    watcher = _run_hyprctl("keyword", "misc:disable_autoreload", "true")
    if watcher.returncode:
        raise ConfigError((f"could not disable Hyprland autoreload: {watcher.stderr.strip() or watcher.stdout.strip()}",))
    snapshot = _snapshot(root, managed)
    old_manifest_bytes = _manifest_path(root).read_bytes() if _manifest_path(root).exists() else None
    old_history_bytes = _history_path(root).read_bytes() if _history_path(root).exists() else None
    _write_history(root, old_manifest, snapshot)
    try:
        _write_outputs(root, build, old_manifest)
    except Exception as exc:
        try:
            _restore_target_state(root, snapshot, old_manifest_bytes, old_history_bytes)
        except Exception as restore_exc:
            raise ConfigError((f"configuration write failed: {exc}", f"automatic file rollback failed: {restore_exc}")) from exc
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError((f"configuration write failed: {exc}; previous files were restored",)) from exc
    success, detail = _reload()
    if not success:
        try:
            _restore_target_state(root, snapshot, old_manifest_bytes, old_history_bytes)
        except Exception as exc:
            rollback_ok, rollback_detail = False, f"file restoration failed: {exc}"
        else:
            rollback_ok, rollback_detail = _reload()
        raise ConfigError(
            (
                f"new configuration failed after reload: {detail}",
                f"automatic rollback {'succeeded' if rollback_ok else 'failed'}: {rollback_detail or 'old configuration restored'}",
            )
        )
    print(f"Applied generated Hyprland configuration under {root / GENERATED_DIR_REL}; reload completed without config errors.")


def rollback() -> None:
    root = _target_root()
    history = _read_history(root)
    old_manifest = _load_manifest(root)
    current_paths = _manifest_files(old_manifest)
    history_paths = {Path(entry["path"]) for entry in history["files"]}
    managed = current_paths | history_paths
    _guard_paths(root, managed, managed)
    watcher = _run_hyprctl("keyword", "misc:disable_autoreload", "true")
    if watcher.returncode:
        raise ConfigError((f"could not disable Hyprland autoreload: {watcher.stderr.strip() or watcher.stdout.strip()}",))
    current_snapshot = _snapshot(root, managed)
    current_manifest_bytes = _manifest_path(root).read_bytes() if _manifest_path(root).exists() else None
    reload_attempted = False
    try:
        _restore_snapshot(root, history["files"])
        old_manifest_data = history.get("manifest")
        if old_manifest_data is None:
            _remove(_manifest_path(root))
        else:
            _write_manifest(root, json.dumps(old_manifest_data, ensure_ascii=True, indent=2, sort_keys=True) + "\n")
        reload_attempted = True
        success, detail = _reload()
        if not success:
            raise ConfigError((f"rollback reload failed: {detail}",))
        _remove(_history_path(root))
        print(f"Rolled back generated Hyprland configuration under {root / GENERATED_DIR_REL}; TOML sources were left unchanged.")
    except Exception as exc:
        try:
            _restore_snapshot(root, current_snapshot)
            if current_manifest_bytes is None:
                _remove(_manifest_path(root))
            else:
                _atomic_write(_manifest_path(root), current_manifest_bytes)
            if reload_attempted:
                restore_ok, restore_detail = _reload()
                if not restore_ok:
                    raise ConfigError((restore_detail or "current configuration reload failed",))
        except Exception as recovery_exc:
            raise ConfigError((f"rollback failed: {exc}", f"current configuration restore failed: {recovery_exc}")) from exc
        if isinstance(exc, ConfigError) and str(exc).startswith("- rollback reload failed:"):
            raise ConfigError((f"{str(exc).removeprefix('- ')}; current configuration was restored",)) from exc
        raise ConfigError((f"rollback failed before reload: {exc}; current configuration was restored",)) from exc


def install() -> None:
    root = _target_root()
    links = {ROOT / "hyprland.lua": root / "hyprland.lua", ROOT / "config" / "manual.lua": root / "config" / "manual.lua"}
    if root.exists() and not root.is_dir():
        raise ConfigError((f"{root}: expected a directory",))
    config_dir = root / "config"
    if config_dir.is_symlink():
        raise ConfigError((f"{config_dir}: refusing to install through a symlinked directory",))
    if config_dir.exists() and not config_dir.is_dir():
        raise ConfigError((f"{config_dir}: expected a directory",))
    for source, destination in links.items():
        if not source.is_file():
            raise ConfigError((f"{source}: hand-maintained source is missing",))
        if destination.is_symlink():
            if destination.resolve() == source.resolve():
                continue
            raise ConfigError((f"{destination}: existing symlink does not point to this repository",))
        if destination.exists():
            raise ConfigError((f"{destination}: existing regular file will not be overwritten",))
    created: list[tuple[Path, Path]] = []
    try:
        for source, destination in links.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(source)
            created.append((source, destination))
    except Exception as exc:
        cleanup_errors: list[str] = []
        for source, destination in reversed(created):
            if destination.is_symlink() and destination.resolve() == source.resolve():
                try:
                    destination.unlink()
                except OSError as cleanup_exc:
                    cleanup_errors.append(f"{destination}: {cleanup_exc}")
        if cleanup_errors:
            raise ConfigError((f"install failed: {exc}", f"partial install cleanup failed: {'; '.join(cleanup_errors)}")) from exc
        raise ConfigError((f"install failed: {exc}; partial links were removed",)) from exc
    print(f"Installed hand-maintained Hyprland entrypoints under {root}; generated files still require `just generate` or `just apply`.")


def migrate_variables() -> None:
    path = CONFIG_DIR / "variables.lua"
    if not path.exists():
        raise ConfigError((f"{path}: legacy variables.lua does not exist",))
    entries: dict[str, str] = {}
    in_table = False
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.split("--", 1)[0].strip()
        if not line:
            continue
        if line == "return {":
            if in_table:
                raise ConfigError((f"{path}:{number}: nested return table is not supported",))
            in_table = True
            continue
        if line == "}":
            in_table = False
            continue
        if not in_table:
            raise ConfigError((f"{path}:{number}: expected a simple return table",))
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?),?", line)
        if match is None:
            raise ConfigError((f"{path}:{number}: only simple key = string entries are supported",))
        try:
            value = ast.literal_eval(match.group(2))
        except (SyntaxError, ValueError) as exc:
            raise ConfigError((f"{path}:{number}: invalid string literal ({exc})",)) from exc
        if not isinstance(value, str):
            raise ConfigError((f"{path}:{number}: variable value must be a string",))
        entries[match.group(1)] = value
    if in_table:
        raise ConfigError((f"{path}: unterminated return table",))
    lines = [
        "# Candidate migration output. Review before saving as config/variables.toml.",
        "# This command does not modify or delete config/variables.lua.",
        "",
        "[meta]",
        f"schema = {json.dumps(SCHEMA)}",
        f"target_hyprland = {json.dumps(TARGET_HYPRLAND)}",
        f"profile = {json.dumps(PROFILE)}",
        "",
        "[commands]",
    ]
    lines.extend(f"{name} = {json.dumps(entries[name], ensure_ascii=True)}" for name in sorted(entries))
    print("\n".join(lines))


def list_config() -> str:
    lines = ["Supported TOML domains:"]
    lines.extend(f"  {name}: {SOURCE_FILES[name].relative_to(ROOT)} -> {MODULE_REL[name]}" for name in SOURCE_FILES)
    lines.extend(
        [
            "\nGenerated output:",
            f"  {AGGREGATE_REL}",
            "  config/.generated-manifest.json",
            "\nAutostart executable allowlist:",
            "  " + " ".join(sorted(ALLOWED_EXECUTABLES)),
            "\nKeymap:",
            keymap.list_keymap(),
        ]
    )
    return "\n".join(lines)


def check() -> None:
    root = _target_root()
    build = _build()
    mismatches = generate(check_only=True)
    if mismatches:
        raise ConfigError(("generated files are out of date: " + ", ".join(mismatches) + "; run `just generate`",))
    entrypoint = ROOT / "hyprland.lua"
    manual = ROOT / "config" / "manual.lua"
    if not entrypoint.exists() or not manual.exists():
        raise ConfigError(("hyprland.lua and config/manual.lua must both exist",))
    for path in (entrypoint, manual, *(_target_path(root, relative) for relative in build.outputs)):
        _lua_syntax_check(path)
    text = entrypoint.read_text(encoding="utf-8")
    for required in ('require("config.manual")', 'require("config.generated")'):
        if required not in text:
            raise ConfigError((f"hyprland.lua: expected {required}",))
    aggregate = _target_path(root, AGGREGATE_REL).read_text(encoding="utf-8")
    for name in DOMAIN_ORDER:
        module = "binds" if name == "keymap" else name
        required = f'require("config.generated.{module}")'
        if required not in aggregate:
            raise ConfigError((f"config/generated.lua: expected {required}",))


def run_tests() -> int:
    return subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]).returncode


def main(argv: list[str] | None = None) -> int:
    commands = ("install", "generate", "check", "list", "test", "apply", "rollback", "migrate-variables")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=commands)
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            install()
        elif args.command == "generate":
            generate()
            print(f"Generated Hyprland modules under {_target_root() / GENERATED_DIR_REL} and synchronized configuration docs.")
        elif args.command == "check":
            check()
            print("TOML sources, generated modules, manifest, docs, entrypoint, and Lua syntax are synchronized.")
        elif args.command == "list":
            print(list_config())
        elif args.command == "test":
            return run_tests()
        elif args.command == "apply":
            apply()
        elif args.command == "rollback":
            rollback()
        elif args.command == "migrate-variables":
            migrate_variables()
    except (ConfigError, keymap.KeymapError) as exc:
        print(f"config: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
