"""Regression tests for preview."""

import os
import shutil

from support import IpreTestCase, path_key


class PreviewTests(IpreTestCase):
    def test_preview_receives_literal_path_and_saves_encoded_identity(self):
        source = self.cwd / "a -> %0A\n"
        source.write_text("selected")
        log = self.root / "preview-args"
        self.env["IPRE_TEST_PREVIEW_LOG"] = str(log)
        self.backend(
            "ipre_action_preview_with_page", "--encoded", path_key(source),
            script='pre() { printf "%s\\0" "$@" > "$IPRE_TEST_PREVIEW_LOG"; }; '
            'source "$1" "${@:2}"',
        )
        self.assertEqual(log.read_bytes(), os.fsencode(source) + b"\0PAGE:1\0")
        self.assertEqual((self.state / "LAST").read_text(), path_key(source) + "\n")

    def test_preview_scroll_uses_entire_space_containing_path(self):
        for ext in ("pdf", "djvu", "txt"):
            source = self.cwd / f"my doc.{ext}"
            source.write_text("preview")
            (self.state / "LAST").write_text(path_key(source) + "\n")
            (self.state / "PAGE_MAX").write_text("3\n")
            for protocol in ("--encoded", "--records"):
                with self.subTest(ext=ext, protocol=protocol):
                    item = path_key(source)
                    if protocol == "--records":
                        item += "\ticon " + source.name
                    (self.state / "PAGE").write_text("1\n")
                    for direction, page in (("down", 2), ("down", 3), ("down", 3),
                                            ("up", 2), ("up", 1), ("up", 1)):
                        result = self.backend("ipre_action_smart_scroll", protocol, direction, item)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        expected = "refresh-preview" if ext != "txt" else f"preview-half-page-{direction}"
                        self.assertEqual(result.stdout.strip(), expected)
                        self.assertEqual((self.state / "PAGE").read_text().strip(),
                                         str(page if ext != "txt" else 1))

    def test_live_grep_keeps_colons_out_of_the_path_field(self):
        if not shutil.which("rg"):
            self.skipTest("ripgrep is needed for live grep")
        source = self.cwd / "colon:name.txt"
        source.write_text("needle:1:2 content\n")
        result = self.backend("ipre_action_rg_stream", "needle")
        self.assertEqual(result.returncode, 0, result.stderr)
        fields = result.stdout.strip().split("\t", 3)
        self.assertEqual(fields[:3], [path_key(source), "1", "1"])
        self.assertIn("colon:name.txt:1:1:needle:1:2 content", fields[3])

    def test_live_grep_selection_jumps_to_colon_named_file(self):
        if not shutil.which("rg"):
            self.skipTest("ripgrep is needed for live grep")
        source = self.cwd / "colon:name.txt"
        source.write_text("needle content\n")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fzf = bin_dir / "fzf"
        fzf.write_text(
            '#!/usr/bin/env zsh\n'
            '"$IPRE_BACKEND_CMD" ipre_action_rg_stream needle | head -n 1\n'
        )
        fzf.chmod(0o755)
        self.env["PATH"] = f"{bin_dir}:{self.env['PATH']}"
        self.backend("ipre_action_live_grep", tty=True)
        self.assertEqual((self.state / "CWD").read_text().strip(), path_key(self.cwd))
        self.assertEqual((self.state / "FOCUS").read_text().strip(), path_key(source))

    def test_live_grep_preview_decodes_the_path_field(self):
        source = self.cwd / "colon:name%.txt"
        source.write_text("needle content\n")
        cache = self.root / "cache"
        cache.mkdir()
        self.env["XDG_CACHE_HOME"] = str(cache)
        encoded = path_key(source)
        result = self.backend("ipre_action_rg_preview", "--encoded", encoded, "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("needle content", result.stdout)
