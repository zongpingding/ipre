"""Command prompt exits must always restore the browser's screen."""

from support import IpreTestCase


class PaletteTests(IpreTestCase):
    def test_shell_prompt_real_ctrl_c_restores_screen(self):
        result = self.backend(
            "ipre_action_probe",
            script='ipre_action_probe() { :; }; source "$1" "$2"; ipre_palette_do_shell_cmd',
            tty=True, responses=[(b"Enter command:", b"\x03")],
        )
        self.assertNotIn("Select execution mode", result.stdout)
        self.assert_ui_is_scoped(result)

    def test_shell_prompt_cancel_and_empty_input_restore_screen(self):
        for prompt in ('vared() { return 1; };', 'vared() { cmd_str=""; };'):
            with self.subTest(prompt=prompt):
                result = self.backend(
                    "ipre_action_probe",
                    script='ipre_action_probe() { :; }; ' + prompt +
                    'source "$1" "$2"; ipre_palette_do_shell_cmd', tty=True,
                )
                self.assertNotIn("continue", result.stdout)
                self.assertNotIn("Select execution mode", result.stdout)
                self.assert_ui_is_scoped(result)

    def test_shell_execution_modes_restore_screen(self):
        for mode in ("b", "n", "invalid"):
            with self.subTest(mode=mode):
                result = self.backend(
                    "ipre_action_probe",
                    script='ipre_action_probe() { :; }; vared() { cmd_str="false"; }; '
                    f'read() {{ mode={mode}; }}; sleep() {{ :; }}; '
                    'source "$1" "$2"; ipre_palette_do_shell_cmd', tty=True,
                )
                self.assert_ui_is_scoped(result)
