from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import config, keymap


BASE = """
[meta]
schema = "1"
target_hyprland = ">=0.55.0"
profile = "test"
[modifiers]
mod = "SUPER"
send = "ALT"
[adjust]
enter = "mod+a"
exit = ["Esc", "Enter"]
reorder = ["h", "j", "k", "l"]
resize = ["Shift+h", "Shift+j", "Shift+k", "Shift+l"]
"""


class KeymapValidationTests(unittest.TestCase):
    def load(self, body: str) -> keymap.Keymap:
        import tomllib

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keymap.toml"
            path.write_text(body, encoding="utf-8")
            return keymap.validate(tomllib.loads(body), path)

    def assertInvalid(self, body: str, *messages: str) -> None:
        import tomllib

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keymap.toml"
            path.write_text(body, encoding="utf-8")
            with self.assertRaises(keymap.KeymapError) as raised:
                keymap.validate(tomllib.loads(body), path)
        for message in messages:
            self.assertIn(message, str(raised.exception))

    def test_normalizes_aliases_and_workspace_physical_codes(self) -> None:
        result = self.load(BASE + '\n[workspace]\nswitch = ["mod+1", "mod+0"]\n')
        workspace = [item.chord.canonical for item in result.bindings if item.section == "workspace"]
        self.assertEqual(workspace, ["SUPER + code:10", "SUPER + code:19"])

    def test_rejects_multiple_modifiers_and_unknown_fields_together(self) -> None:
        body = BASE + '\n[window]\nfocus = "mod+Shift+h"\nunknown = "mod+q"\n'
        self.assertInvalid(body, "window.focus", "at most one modifier and one key", "window.unknown: unknown action")

    def test_rejects_duplicate_and_universal_local_conflicts(self) -> None:
        body = BASE + """
[window]
close = "mod+q"
fullscreen = "mod+q"
[hardware]
mute = "mod+q"
"""
        self.assertInvalid(body, "duplicate chord", "conflicts with universal binding")

    def test_rejects_incomplete_adjust_mode(self) -> None:
        body = BASE.replace('exit = ["Esc", "Enter"]', 'exit = "Esc"').replace(
            'resize = ["Shift+h", "Shift+j", "Shift+k", "Shift+l"]', 'resize = ["Shift+h"]'
        )
        self.assertInvalid(body, "adjust.exit", "both Esc and Enter", "adjust.resize")

    def test_missing_optional_sections_do_not_create_hidden_bindings(self) -> None:
        result = self.load(BASE)
        self.assertTrue(result.bindings)
        self.assertTrue(all(item.section == "adjust" for item in result.bindings))

    def test_extra_exec_is_allowlisted_and_raw_dispatch_is_rejected(self) -> None:
        valid = BASE + """
[extra.exec.reload_bar]
chord = "mod+r"
command = "waybar"
"""
        result = self.load(valid)
        self.assertEqual(result.extra_exec[0].command, "waybar")
        shell = valid.replace('command = "waybar"', 'command = "sh -c \'waybar && true\'"')
        self.assertEqual(self.load(shell).extra_exec[0].command, "sh -c 'waybar && true'")
        invalid = valid.replace('command = "waybar"', 'command = "hyprctl dispatch reload"')
        self.assertInvalid(invalid, "raw Hyprland dispatch/control commands are not allowed")
        unknown = valid.replace('command = "waybar"', 'command = "sh -c \'waybar && unknown-command\'"')
        self.assertInvalid(unknown, "executable is not in the controlled process allowlist")
        direct_shell = valid.replace('command = "waybar"', 'command = "waybar; true"')
        self.assertInvalid(direct_shell, "shell operators require sh -c")

    def test_rendering_is_deterministic_and_contains_header(self) -> None:
        result = self.load(BASE + '\n[window]\nclose = "mod+q"\n')
        self.assertEqual(keymap.render_lua(result), keymap.render_lua(result))
        self.assertEqual(keymap.render_doc(result), keymap.render_doc(result))
        self.assertIn("GENERATED FILE. DO NOT EDIT.", keymap.render_lua(result))
        self.assertIn(result.source_hash, keymap.render_doc(result))

    def test_keymap_doc_lists_the_complete_interface(self) -> None:
        documentation = keymap.render_doc(self.load(BASE))
        self.assertIn("[meta]", documentation)
        self.assertIn("[modifiers]", documentation)
        self.assertIn("`adjust.enter`", documentation)
        self.assertIn("`adjust.exit`", documentation)
        self.assertIn("`adjust.reorder`", documentation)
        self.assertIn("`adjust.resize`", documentation)
        for section, actions in keymap.SECTION_ACTIONS.items():
            for action in actions:
                self.assertIn(f"| `{section}` | `{action}` |", documentation)
        self.assertIn("| `extra.exec` | `named command` |", documentation)
        self.assertIn("[extra.exec.reload_bar]", documentation)
        self.assertIn("`mouse:<number>`", documentation)
        self.assertIn("`code:<number>`", documentation)
        self.assertIn("`XF86AudioRaiseVolume`", documentation)
        self.assertIn("`F1`-`F12`", documentation)

    def test_error_accepts_one_message_without_splitting_it(self) -> None:
        self.assertEqual(str(keymap.KeymapError("one error")), "- one error")

    def test_accepts_function_keys_as_spares_and_rejects_unknown_keys(self) -> None:
        result = self.load(BASE + '\n[window]\nclose = "F12"\n')
        self.assertEqual(result.bindings[0].chord.key, "F12")
        self.assertInvalid(BASE + '\n[window]\nclose = "not-a-key"\n', "unsupported key")
        self.assertInvalid(BASE + '\n[hardware]\nmute = "XF86"\n', "unsupported key")

    def test_renders_hyprland_key_names_and_shell_commands(self) -> None:
        result = self.load(
            BASE
            + '\n[workspace]\nadjacent_focus = ["mod+leftbracket", "mod+rightbracket"]\n'
            + '\n[utility]\nscreenshot_region = "Print"\nzoom_in = "mod+equal"\n'
            + '\n[application]\nterminal = "mod+Enter"\n'
        )
        output = keymap.render_lua(result)
        self.assertIn('hl.bind("SUPER + bracketleft"', output)
        self.assertIn('hl.bind("SUPER + bracketright"', output)
        self.assertIn('hl.bind("SUPER + equal"', output)
        self.assertIn('hl.bind("SUPER + Return"', output)
        self.assertIn('sh -c', output)
        self.assertIn('grim -g \\"$(slurp)\\" - | wl-copy', output)

    def test_lua_syntax_precheck_is_optional(self) -> None:
        with mock.patch.object(config, "_lua_binary", return_value=None):
            with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
                config._lua_syntax_check(Path("candidate.lua"))
        self.assertIn("skipped syntax check", stderr.getvalue())

    def test_pointer_bindings_use_the_mouse_key_without_unknown_options(self) -> None:
        result = self.load(BASE + '\n[pointer]\nmove = "mod+mouse:left"\n')
        output = keymap.render_lua(result)
        self.assertIn('hl.bind("SUPER + mouse:272", hl.dsp.window.drag())', output)
        self.assertNotIn("mouse = true", output)

    def test_rejects_directional_actions_with_ambiguous_keys(self) -> None:
        self.assertInvalid(BASE + '\n[window]\nfocus = "mod+x"\n', "directions are unambiguous")

    def test_lua_binary_does_not_fall_back_to_an_unversioned_interpreter(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(config.shutil, "which", return_value=None) as which:
                self.assertIsNone(config._lua_binary())
                which.assert_called_once_with("lua5.5")

    def test_universal_bindings_are_emitted_for_normal_and_adjust(self) -> None:
        result = self.load(BASE + '\n[hardware]\nmute = "XF86AudioMute"\n')
        output = keymap.render_lua(result)
        self.assertEqual(output.count('XF86AudioMute'), 1)
        self.assertIn('hl.bind("XF86AudioMute"', output)
        self.assertIn('{ locked = true, submap_universal = true }', output)
        self.assertNotIn('submap = "adjust"', output)

        repeated = self.load(BASE + '\n[hardware]\nvolume_up = "XF86AudioRaiseVolume"\n')
        self.assertIn(
            '{ locked = true, repeating = true, submap_universal = true }',
            keymap.render_lua(repeated),
        )

    def test_adjust_bindings_use_hyprland_submap_api(self) -> None:
        result = self.load(BASE)
        output = keymap.render_lua(result)
        self.assertIn('hl.define_submap("adjust", function()', output)
        self.assertIn('\thl.bind("Escape", hl.dsp.submap("reset"))', output)
        self.assertIn(
            '\thl.bind("H", hl.dsp.window.swap({ direction = "left" }), { repeating = true })',
            output,
        )
        self.assertIn(
            '\thl.bind("SHIFT + H", hl.dsp.window.resize({ x = -40, y = 0, relative = true }), { repeating = true })',
            output,
        )
        self.assertIn('\thl.bind("catchall", hl.dsp.no_op(), { ignore_mods = true })', output)
        self.assertNotIn('hl.bind({', output)
        self.assertNotIn('focus_cycle', output)
        self.assertNotIn('["repeat"]', output)

    def test_known_hyprland_dispatcher_shapes(self) -> None:
        result = self.load(
            BASE
            + '\n[window]\ncycle_window = "mod+Tab"\n'
            + '\n[workspace]\nscratchpad_toggle = "mod+s"\nmove_follow = "send+1"\nadjacent_move = "send+leftbracket"\n'
            + '\n[monitor]\nmove_next_follow = "send+o"\n'
        )
        output = keymap.render_lua(result)
        self.assertIn('hl.dsp.window.cycle_next({ next = true })', output)
        self.assertIn('hl.dsp.workspace.toggle_special("scratchpad")', output)
        self.assertIn('hl.dsp.window.move({ workspace = "10", follow = true })', output)
        self.assertIn('hl.dsp.window.move({ workspace = "e-1", follow = true })', output)
        self.assertIn('hl.dsp.window.move({ monitor = "+1", follow = true })', output)

    def test_uses_cachyos_noctalia_message_commands(self) -> None:
        result = self.load(
            BASE
            + '\n[noctalia]\nlauncher = "mod+Space"\n'
            + '\n[hardware]\nvolume_up = "XF86AudioRaiseVolume"\n'
        )
        output = keymap.render_lua(result)
        self.assertIn('noctalia msg panel-toggle launcher', output)
        self.assertIn('noctalia msg volume-up', output)
        self.assertNotIn('noctalia-shell ipc call', output)


class GeneratedFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.target = Path(self.directory.name) / "hypr"
        with mock.patch.dict(os.environ, {"HYPRLAND_CONFIG_ROOT": str(self.target)}, clear=False):
            config.generate()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_repository_outputs_are_synchronized(self) -> None:
        with mock.patch.dict(os.environ, {"HYPRLAND_CONFIG_ROOT": str(self.target)}, clear=False):
            config.check()

    def test_manual_generated_drift_is_detected(self) -> None:
        output = config._target_path(self.target, config.MODULE_REL["keymap"])
        original = output.read_text(encoding="utf-8")
        try:
            output.write_text(original + "-- drift\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"HYPRLAND_CONFIG_ROOT": str(self.target)}, clear=False):
                self.assertIn(str(output), config.generate(check_only=True))
        finally:
            output.write_text(original, encoding="utf-8")

    def test_generate_refuses_a_live_repository_root(self) -> None:
        with mock.patch.dict(os.environ, {"HYPRLAND_CONFIG_ROOT": str(keymap.ROOT)}, clear=False):
            with self.assertRaises(keymap.KeymapError) as raised:
                config.generate()
        self.assertIn("just apply", str(raised.exception))

    def test_target_root_is_required_from_environment(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(keymap.KeymapError) as raised:
                config.generate()
        self.assertEqual(
            str(raised.exception),
            '- HYPRLAND_CONFIG_ROOT is not set; define it once, for example `export HYPRLAND_CONFIG_ROOT="$HOME/.config/hypr"`',
        )


if __name__ == "__main__":
    unittest.main()
