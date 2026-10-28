"""Detail columns never become search keys or operation paths."""

import re
import subprocess

from support import IpreTestCase, path_key


class DetailTests(IpreTestCase):
    def test_details_preserve_names_sorting_and_file_operations(self):
        source = self.cwd / "a -> b\t%0A\n.txt"
        source.write_text("payload")
        source.chmod(0o640)
        folder = self.cwd / "directory"
        folder.mkdir()
        broken = self.cwd / "broken-link"
        broken.symlink_to("missing\t\n")
        for depth in ("1", "0"):
            with self.subTest(depth=depth):
                (self.state / "RAM_DEPTH").write_text(depth + "\n")
                (self.state / "VIEW").write_text("compact\n")
                compact = self.backend("ipre_action_run").stdout.splitlines()
                self.backend("ipre_action_toggle_view")
                result = self.backend("ipre_action_run")
                self.assertEqual(result.returncode, 0, result.stderr)
                detailed = [row.split("\t") for row in result.stdout.splitlines()]
                self.assertEqual(sorted("\t".join(row[:2]) for row in detailed), sorted(compact))
                self.assertTrue(all(len(row) == 4 for row in detailed))
                by_key = {row[0]: row for row in detailed}
                self.assertIn("0640", by_key[path_key(source)][2])
                self.assertIn("7 B", by_key[path_key(source)][2])
                self.assertIn("broken-link", by_key[path_key(broken)][2])
                self.assertEqual(r"-> missing\t\n", by_key[path_key(broken)][3])
                # The prefix has one width regardless of filename/type/size.
                self.assertEqual(len({len(row[2]) for row in detailed}), 1)
                record = "\t".join(by_key[path_key(source)])
                self.backend("ipre_action_copy", "--records", record)
                self.assertEqual((self.state / "CLIP").read_text(), f"COPY\n{path_key(source)}\n")

    def test_fzf_search_excludes_metadata_and_encoded_path(self):
        # Same field settings as the browser, including fzf's display transform.
        for detailed in (False, True):
            record = "/tmp/hiddenidentity\tfilename.txt"
            record += "\tmetadataonly 0640\t-> targetonly" if detailed else ""
            record += "\n"
            for query, found in (("filename", True), ("metadataonly", False),
                                 ("hiddenidentity", False), ("targetonly", False)):
                with self.subTest(detailed=detailed, query=query):
                    result = subprocess.run(
                        ["fzf", "--delimiter=\t", "--with-nth=" + ("3,2,4" if detailed else "2"),
                         "--nth=" + ("2" if detailed else "1"), "--filter", query],
                        input=record, text=True, capture_output=True, env=self.env, timeout=5,
                    )
                    self.assertEqual(result.returncode, 0 if found else 1)
                    self.assertEqual(result.stdout, record if found else "")

    def test_real_fzf_renders_aligned_attributes_before_names(self):
        self.env["IPRE_ICONS"] = "1"
        (self.state / "RAM_DEPTH").write_text("1\n")
        (self.state / "VIEW").write_text("detailed\n")
        (self.cwd / "directory").mkdir()
        (self.cwd / "a").write_text("short")
        (self.cwd / "long name 中文 -> data.txt").write_text("long")
        (self.cwd / "link").symlink_to("a")
        # Sparse file verifies that large byte counts cannot push later columns.
        with (self.cwd / "large").open("wb") as stream:
            stream.truncate(10**12)
        records = self.backend("ipre_action_run").stdout.splitlines()
        result = self.backend(
            "ipre_action_probe",
            script='ipre_action_probe() { :; }; source "$1" "$2"; '
            'ipre_action_run | fzf --height=20 --reverse --no-hscroll '
            '--delimiter=$\'\\t\' --with-nth=3,2,4 --nth=2',
            tty=True, expected_returncode=130,
            responses=(("long name 中文".encode(), b"\x11"),),
        )
        rendered = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", result.stdout)
        widths = set()
        for record in records:
            key, name, metadata, suffix = record.split("\t")
            prefix = (metadata + "\t").expandtabs(8)
            widths.add(len(prefix))
            self.assertIn(prefix + name, rendered)
        self.assertEqual(len(widths), 1)
