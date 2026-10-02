"""Regression tests for preview."""

import os
import re
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
        self.assertIn("\x1b[31mneedle\x1b[0m", fields[3])
        display = re.sub(r"\x1b\[[0-9;]*m", "", fields[3])
        self.assertEqual(display, "colon:name.txt:1:1:needle:1:2 content")

    def test_live_grep_preserves_special_paths_and_escapes_content_controls(self):
        if not shutil.which("rg"):
            self.skipTest("ripgrep is needed for live grep")
        source = self.cwd / "空 格:percent%\\tab\tline\nreset\x1b[0m"
        source.write_text("unmatched\n前缀\tneedle\\tail\x1b[2J needle\n")
        result = self.backend("ipre_action_rg_stream", "needle")
        self.assertEqual(result.returncode, 0, result.stderr)
        records = result.stdout.splitlines()
        self.assertEqual(len(records), 1)
        fields = records[0].split("\t")
        self.assertEqual(len(fields), 4)
        self.assertEqual(fields[:3], [path_key(source), "2", "8"])
        self.assertEqual(fields[3].count("\x1b[31mneedle\x1b[0m"), 2)
        display = re.sub(r"\x1b\[[0-9;]*m", "", fields[3])
        self.assertNotIn("\x1b", display)
        self.assertTrue(display.endswith(r"前缀\tneedle\\tail\x1B[2J needle"))

    def test_live_grep_empty_missing_and_invalid_queries_have_no_records(self):
        if not shutil.which("rg"):
            self.skipTest("ripgrep is needed for live grep")
        (self.cwd / "sample.txt").write_text("needle content\n")
        for query in ("", "absent", "["):
            with self.subTest(query=query):
                result = self.backend("ipre_action_rg_stream", "--", query)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_live_grep_real_fzf_reload_and_selection(self):
        if not shutil.which("rg") or not shutil.which("fzf"):
            self.skipTest("ripgrep and fzf are needed for live grep")
        directory = self.cwd / "nested"
        directory.mkdir()
        source = directory / "colon:name.txt"
        source.write_text("needle content\n")
        self.backend(
            "ipre_action_live_grep", tty=True,
            responses=((b"Ripgrep", b"needle"), (b"colon:name.txt", b"\r")),
        )
        self.assertEqual((self.state / "CWD").read_text().strip(), path_key(directory))
        self.assertEqual((self.state / "FOCUS").read_text().strip(), path_key(source))

    def test_live_grep_real_fzf_multi_selection_deduplicates_paths(self):
        if not shutil.which("rg") or not shutil.which("fzf"):
            self.skipTest("ripgrep and fzf are needed for live grep")
        first = self.cwd / "first:file.txt"
        second = self.cwd / "second file.txt"
        first.write_text("needle one\nneedle two\n")
        second.write_text("needle three\n")
        self.backend(
            "ipre_action_live_grep", tty=True,
            responses=((b"Ripgrep", b"needle"), (b"3/3", b"\x1ba\r")),
        )
        selected = (self.state / "SELECT").read_text().splitlines()
        self.assertCountEqual(selected, [path_key(first), path_key(second)])
        self.assertIn((self.state / "FOCUS").read_text().strip(), selected)

    def test_live_grep_real_fzf_switches_to_fuzzy_search(self):
        if not shutil.which("rg") or not shutil.which("fzf"):
            self.skipTest("ripgrep and fzf are needed for live grep")
        source = self.cwd / "colon:name.txt"
        source.write_text("needle content\n")
        self.backend(
            "ipre_action_live_grep", tty=True,
            responses=((b"Ripgrep", b"needle"), (b"colon:name.txt", b"\x1bf"),
                       (b"Fuzzy", b"colon\r")),
        )
        self.assertEqual((self.state / "FOCUS").read_text().strip(), path_key(source))

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
