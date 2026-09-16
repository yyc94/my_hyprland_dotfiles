from __future__ import annotations

import io
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import config


META = '''
[meta]
schema = "1"
target_hyprland = ">=0.55.0"
profile = "test"
'''


class ConfigSchemaTests(unittest.TestCase):
    def make_sources(self, directory: Path) -> dict[str, Path]:
        sources = {name: directory / f"{name}.toml" for name in config.SOURCE_FILES}
        sources["variables"].write_text(META + '\n[commands]\nterminal = "kitty"\nfile_manager = "yazi"\nbrowser = "zen"\ncalculator = "calc"\nsystem_monitor = "btop"\n', encoding="utf-8")
        sources["monitors"].write_text(
            META
            + '\n[[monitor]]\noutput = "DP-1"\nmode = "preferred"\nposition = { x = 0, y = 0 }\nscale = 1.25\ntransform = "90"\nvrr = "on"\n',
            encoding="utf-8",
        )
        sources["workspaces"].write_text(
            META + '\n[[workspace]]\nworkspace = "1"\nmonitor = "DP-1"\ndefault = true\npersistent = true\nlayout = "master"\n',
            encoding="utf-8",
        )
        sources["input"].write_text(
            META
            + '\n[keyboard]\nlayout = "us"\nrepeat_rate = 30\nrepeat_delay = 500\nnumlock_by_default = true\n\n[mouse]\nfollow = "follow"\nfocus_on_close = "mru"\nsensitivity = -0.25\naccel_profile = "flat"\nnatural_scroll = true\n',
            encoding="utf-8",
        )
        sources["rules"].write_text(
            META
            + '''
[[windowrule]]
name = "floating-calculator"

[windowrule.match]
class = "org.example.Calculator"

[windowrule.effects]
float = true
center = true
size = { x = 800, y = 600 }

[[layerrule]]
name = "no-blur-panel"

[layerrule.match]
namespace = "panel"

[layerrule.effects]
blur = true
''',
            encoding="utf-8",
        )
        sources["environment"].write_text(META + '\n[environment]\nXCURSOR_SIZE = "24"\n', encoding="utf-8")
        sources["autostart"].write_text(
            META + '\n[[exec_once]]\nname = "status-bar"\ncommand = ["waybar", "--bar"]\n', encoding="utf-8"
        )
        return sources

    def test_all_domains_compile_to_hyprland_lua(self) -> None:
        with tempfile.TemporaryDirectory(dir=config.ROOT) as directory:
            paths = self.make_sources(Path(directory))
            with mock.patch.object(config, "SOURCE_FILES", paths):
                build = config._build()
        self.assertIn('hl.monitor({', build.outputs[config.MODULE_REL["monitors"]])
        self.assertIn('position = "0x0"', build.outputs[config.MODULE_REL["monitors"]])
        self.assertIn('scale = "1.25"', build.outputs[config.MODULE_REL["monitors"]])
        self.assertIn("transform = 1", build.outputs[config.MODULE_REL["monitors"]])
        self.assertIn("vrr = 1", build.outputs[config.MODULE_REL["monitors"]])
        self.assertIn('hl.workspace_rule({', build.outputs[config.MODULE_REL["workspaces"]])
        self.assertIn("kb_layout = \"us\"", build.outputs[config.MODULE_REL["input"]])
        self.assertIn("follow_mouse = 1", build.outputs[config.MODULE_REL["input"]])
        self.assertIn('hl.window_rule({', build.outputs[config.MODULE_REL["rules"]])
        self.assertIn("size = { 800, 600 }", build.outputs[config.MODULE_REL["rules"]])
        self.assertIn('hl.layer_rule({', build.outputs[config.MODULE_REL["rules"]])
        self.assertIn('hl.env("XCURSOR_SIZE", "24")', build.outputs[config.MODULE_REL["environment"]])
        self.assertIn('hl.on("hyprland.start"', build.outputs[config.MODULE_REL["autostart"]])
        self.assertIn('hl.exec_cmd("waybar --bar")', build.outputs[config.MODULE_REL["autostart"]])
        manifest = json.loads(build.manifest)
        self.assertIn("config/keymap.toml", manifest["sources"])

    def test_monitor_scale_matches_hyprland_lower_bound(self) -> None:
        with tempfile.TemporaryDirectory(dir=config.ROOT) as directory:
            paths = self.make_sources(Path(directory))
            paths["monitors"].write_text(META + '\n[[monitor]]\noutput = "DP-1"\nscale = 0.1\n', encoding="utf-8")
            with mock.patch.object(config, "SOURCE_FILES", paths):
                with self.assertRaises(config.ConfigError) as raised:
                    config._build()
        self.assertIn("monitors.toml: monitor[0].scale: must be >= 0.25", str(raised.exception))

    def test_unknown_schema_and_invalid_exec_are_reported(self) -> None:
        with tempfile.TemporaryDirectory(dir=config.ROOT) as directory:
            paths = self.make_sources(Path(directory))
            paths["monitors"].write_text(META + '\n[[monitor]]\noutput = "DP-1"\nunknown = true\n', encoding="utf-8")
            paths["autostart"].write_text(
                META + '\n[[exec_once]]\nname = "bad"\ncommand = ["sh", "-c", "echo bad"]\n', encoding="utf-8"
            )
            with mock.patch.object(config, "SOURCE_FILES", paths):
                with self.assertRaises(config.ConfigError) as raised:
                    config._build()
        self.assertIn("unknown field", str(raised.exception))
        self.assertIn("controlled process allowlist", str(raised.exception))

    def test_invalid_toml_encoding_is_reported_as_a_config_error(self) -> None:
        with tempfile.TemporaryDirectory(dir=config.ROOT) as directory:
            paths = self.make_sources(Path(directory))
            paths["monitors"].write_bytes(b"[meta]\nschema = \"1\"\ntarget_hyprland = \"\xff\"")
            with mock.patch.object(config, "SOURCE_FILES", paths):
                with self.assertRaises(config.ConfigError) as raised:
                    config._build()
        self.assertIn("invalid TOML", str(raised.exception))

    def test_missing_application_command_is_a_compile_error(self) -> None:
        with tempfile.TemporaryDirectory(dir=config.ROOT) as directory:
            paths = self.make_sources(Path(directory))
            paths["variables"].write_text(META + '\n[commands]\nterminal = "kitty"\n', encoding="utf-8")
            with mock.patch.object(config, "SOURCE_FILES", paths):
                with self.assertRaises(config.ConfigError) as raised:
                    config._build()
        self.assertIn("missing variables.commands", str(raised.exception))


class DeploymentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.target = Path(self.directory.name) / "hypr"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def env(self) -> dict[str, str]:
        return {"HYPRLAND_CONFIG_ROOT": str(self.target)}

    def test_generate_check_and_manifest_are_deterministic(self) -> None:
        with mock.patch.dict(os.environ, self.env(), clear=False):
            config.generate()
            first_manifest = (self.target / config.MANIFEST_REL).read_text(encoding="utf-8")
            self.assertEqual([], config.generate(check_only=True))
            config.generate()
            self.assertEqual(first_manifest, (self.target / config.MANIFEST_REL).read_text(encoding="utf-8"))
        self.assertTrue((self.target / config.AGGREGATE_REL).exists())
        self.assertIn("config/generated/binds.lua", first_manifest)

    def test_generate_writes_aggregate_after_its_modules(self) -> None:
        writes: list[Path] = []
        original_write = config._atomic_write

        def record_write(path: Path, content: str | bytes) -> None:
            if path.is_relative_to(self.target):
                writes.append(path.relative_to(self.target))
            original_write(path, content)

        with mock.patch.object(config, "_atomic_write", side_effect=record_write):
            with mock.patch.dict(os.environ, self.env(), clear=False):
                config.generate()
        aggregate_index = writes.index(config.AGGREGATE_REL)
        module_indexes = [writes.index(relative) for relative in config.MODULE_REL.values()]
        self.assertGreater(aggregate_index, max(module_indexes))

    def test_generate_restores_target_and_docs_when_a_doc_write_fails(self) -> None:
        docs = {path: path.read_bytes() if path.exists() else None for path in (config.DOC_DIR / "KEYMAP.md", config.DOC_DIR / "CONFIG.md")}
        original_write = config._atomic_write
        failed = False

        def fail_config_doc(path: Path, content: str | bytes) -> None:
            nonlocal failed
            if path == config.DOC_DIR / "CONFIG.md" and not failed:
                failed = True
                raise OSError("simulated documentation failure")
            original_write(path, content)

        with mock.patch.object(config, "_atomic_write", side_effect=fail_config_doc):
            with mock.patch.dict(os.environ, self.env(), clear=False):
                with self.assertRaises(config.ConfigError) as raised:
                    config.generate()
        self.assertIn("previous files were restored", str(raised.exception))
        self.assertFalse((self.target / config.MANIFEST_REL).exists())
        for path, content in docs.items():
            self.assertEqual(content, path.read_bytes() if path.exists() else None)

    def test_generated_symlink_is_never_overwritten(self) -> None:
        generated = self.target / config.GENERATED_DIR_REL
        generated.mkdir(parents=True)
        outside = Path(self.directory.name) / "outside.lua"
        outside.write_text("-- external\n", encoding="utf-8")
        (generated / "binds.lua").symlink_to(outside)
        with mock.patch.dict(os.environ, self.env(), clear=False):
            with self.assertRaises(config.ConfigError) as raised:
                config.generate()
        self.assertIn("refusing to manage a symlink", str(raised.exception))
        self.assertEqual("-- external\n", outside.read_text(encoding="utf-8"))

    def test_install_creates_only_expected_hand_lua_links(self) -> None:
        with mock.patch.dict(os.environ, self.env(), clear=False):
            config.install()
        self.assertTrue((self.target / "hyprland.lua").is_symlink())
        self.assertTrue((self.target / "config" / "manual.lua").is_symlink())
        self.assertEqual(config.ROOT / "hyprland.lua", (self.target / "hyprland.lua").resolve())

    def test_install_rejects_external_symlink(self) -> None:
        self.target.mkdir(parents=True)
        external = Path(self.directory.name) / "external.lua"
        external.write_text("-- external\n", encoding="utf-8")
        (self.target / "hyprland.lua").symlink_to(external)
        with mock.patch.dict(os.environ, self.env(), clear=False):
            with self.assertRaises(config.ConfigError) as raised:
                config.install()
        self.assertIn("existing symlink does not point", str(raised.exception))

    def test_install_rejects_symlinked_config_directory(self) -> None:
        self.target.mkdir(parents=True)
        external = Path(self.directory.name) / "external"
        external.mkdir()
        (self.target / "config").symlink_to(external, target_is_directory=True)
        with mock.patch.dict(os.environ, self.env(), clear=False):
            with self.assertRaises(config.ConfigError) as raised:
                config.install()
        self.assertIn("refusing to install through a symlinked directory", str(raised.exception))

    def test_corrupt_manifest_is_rejected(self) -> None:
        with mock.patch.dict(os.environ, self.env(), clear=False):
            config.generate()
        manifest_path = self.target / config.MANIFEST_REL
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"][0]["sha256"] = "bad"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(config.ConfigError) as raised:
            config._load_manifest(self.target)
        self.assertIn("invalid file entry", str(raised.exception))

    def test_migrate_variables_only_prints_candidate(self) -> None:
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            config.migrate_variables()
        output = stdout.getvalue()
        self.assertIn("[commands]", output)
        self.assertIn('terminal = "kitty"', output)
        self.assertIn("does not modify", output)

    def test_generated_entrypoint_loads_with_a_fake_hyprland_api(self) -> None:
        lua = shutil.which("lua5.5") or shutil.which("lua")
        if lua is None:
            self.skipTest("no Lua interpreter available")
        with mock.patch.dict(os.environ, self.env(), clear=False):
            config.generate()
        script = (
            "local function node()\n"
            "    local value = {}\n"
            "    setmetatable(value, {\n"
            "        __index = function() return node() end,\n"
            "        __call = function() return function() end end,\n"
            "    })\n"
            "    return value\n"
            "end\n"
            "hl = { dsp = node() }\n"
            "function hl.bind() end\n"
            "function hl.config() end\n"
            "function hl.monitor() end\n"
            "function hl.workspace_rule() end\n"
            "function hl.window_rule() end\n"
            "function hl.layer_rule() end\n"
            "function hl.env() end\n"
            "function hl.on() end\n"
            "function hl.exec_cmd() end\n"
            "function hl.define_submap(_, callback) callback() end\n"
            "function hl.dispatch() end\n"
            f"package.path = {json.dumps(str(config.ROOT / '?.lua'))} .. ';' .. {json.dumps(str(self.target / '?.lua'))} .. ';' .. package.path\n"
            f"dofile({json.dumps(str(config.ROOT / 'hyprland.lua'))})\n"
        )
        result = subprocess.run([lua, "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class ApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.target = root / "target"
        self.fake_hyprctl = root / "hyprctl"
        self.fake_hyprctl.write_text(
            '''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
if args == ["-j", "configerrors"]:
    print(os.environ.get("FAKE_CONFIG_ERRORS", "[]"))
    raise SystemExit(0)
if args[:1] == ["keyword"]:
    raise SystemExit(1 if os.environ.get("FAKE_FAIL_KEYWORD") == "1" else 0)
if args == ["reload"]:
    count_path = Path(os.environ["FAKE_RELOAD_COUNT"])
    count = int(count_path.read_text() or "0") if count_path.exists() else 0
    count_path.write_text(str(count + 1))
    if os.environ.get("FAKE_FAIL_FIRST_RELOAD") == "1" and count == 0:
        raise SystemExit(1)
    if os.environ.get("FAKE_FAIL_ALL_RELOADS") == "1":
        raise SystemExit(1)
    raise SystemExit(0)
raise SystemExit(0)
''',
            encoding="utf-8",
        )
        self.fake_hyprctl.chmod(self.fake_hyprctl.stat().st_mode | stat.S_IXUSR)
        self.environment = {
            "HYPRLAND_CONFIG_ROOT": str(self.target),
            "HYPRCTL": str(self.fake_hyprctl),
            "FAKE_RELOAD_COUNT": str(root / "reload.count"),
        }

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_apply_and_rollback_cover_all_generated_files(self) -> None:
        with mock.patch.dict(os.environ, self.environment, clear=False):
            config.apply()
            self.assertTrue((self.target / config.HISTORY_REL).exists())
            self.assertTrue((self.target / config.MANIFEST_REL).exists())
            config.rollback()
        self.assertFalse((self.target / config.MANIFEST_REL).exists())
        self.assertFalse((self.target / config.HISTORY_REL).exists())
        self.assertFalse((self.target / config.AGGREGATE_REL).exists())

    def test_reload_failure_restores_files_and_previous_history(self) -> None:
        with mock.patch.dict(os.environ, self.environment, clear=False):
            config.apply()
            before = (self.target / config.AGGREGATE_REL).read_bytes()
            Path(self.environment["FAKE_RELOAD_COUNT"]).write_text("0", encoding="utf-8")
            with mock.patch.dict(os.environ, {"FAKE_FAIL_FIRST_RELOAD": "1"}, clear=False):
                with self.assertRaises(config.ConfigError) as raised:
                    config.apply()
        self.assertIn("automatic rollback succeeded", str(raised.exception))
        self.assertEqual(before, (self.target / config.AGGREGATE_REL).read_bytes())

    def test_existing_errors_block_candidate_install(self) -> None:
        self.environment["FAKE_CONFIG_ERRORS"] = json.dumps(["old error"])
        with mock.patch.dict(os.environ, self.environment, clear=False):
            with self.assertRaises(config.ConfigError) as raised:
                config.apply()
        self.assertIn("existing Hyprland configuration errors", str(raised.exception))
        self.assertFalse((self.target / config.AGGREGATE_REL).exists())

    def test_rollback_reload_failure_restores_current_files(self) -> None:
        with mock.patch.dict(os.environ, self.environment, clear=False):
            config.apply()
            current = (self.target / config.AGGREGATE_REL).read_bytes()
            with mock.patch.dict(os.environ, {"FAKE_FAIL_ALL_RELOADS": "1"}, clear=False):
                with self.assertRaises(config.ConfigError) as raised:
                    config.rollback()
        self.assertIn("rollback reload failed", str(raised.exception))
        self.assertEqual(current, (self.target / config.AGGREGATE_REL).read_bytes())
        self.assertTrue((self.target / config.HISTORY_REL).exists())


if __name__ == "__main__":
    unittest.main()
