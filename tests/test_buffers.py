"""Regression tests for buffers."""



from support import IpreTestCase, path_key


class BuffersTests(IpreTestCase):
    def test_bookmark_and_selection_picker_decode_paths_with_controls(self):
        folder = self.cwd / "folder\n%0A"
        folder.mkdir()
        source = folder / "a -> b\t.txt"
        source.write_text("selected")
        for action in ("bookmark", "mark"):
            self.backend(f"ipre_action_{action}", "--encoded", path_key(source))
        self.assertEqual((self.state / "BOOKMARKS").read_text(), path_key(source) + "\n")
        self.assertEqual((self.state / "SELECT").read_text(), path_key(source) + "\n")
        result = self.backend(
            "ipre_action_open_bookmarks",
            script='fzf() { cat; }; source "$1" "$2"',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state / "CWD").read_text(), path_key(folder) + "\n")
        self.assertEqual((self.state / "FOCUS").read_text(), path_key(source) + "\n")

    def test_buffer_editor_roundtrips_escaped_paths(self):
        source = self.cwd / "a -> %0A\n\\tail"
        source.write_text("selected")
        self.backend("ipre_action_copy", "--encoded", path_key(source))
        self.backend("ipre_action_mark", "--encoded", path_key(source))
        editor = self.root / "keep-editor"
        editor.write_text("#!/bin/sh\nexit 0\n")
        editor.chmod(0o755)
        self.env["EDITOR"] = str(editor)
        self.backend(
            "ipre_action_show_buffers",
            script='read() { choice=v; }; clear() { :; }; source "$1" "$2"',
            tty=True,
        )
        self.assertEqual((self.state / "CLIP").read_text(), f"COPY\n{path_key(source)}\n")
        self.assertEqual((self.state / "SELECT").read_text(), path_key(source) + "\n")
