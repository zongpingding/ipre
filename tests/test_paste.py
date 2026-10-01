"""Regression tests for paste."""

import os
import subprocess

from support import IpreTestCase, BACKEND, path_key


class PasteTests(IpreTestCase):
    def test_encoded_records_preserve_special_names_through_copy_and_cut(self):
        names = ["a -> b.txt", "literal%0A%09", "tab\tname", "tail\n", "中文\\name.txt", " leading and trailing "]
        for i, name in enumerate(names):
            (self.cwd / name).write_text(str(i))
        raw_name = b"invalid-\xff.txt"
        raw_path = os.fsencode(self.cwd) + b"/" + raw_name
        with open(raw_path, "wb") as file:
            file.write(b"raw bytes")
        broken = self.cwd / "broken -> link"
        broken.symlink_to("missing")
        destination = self.root / "dest\n%0A"
        destination.mkdir()
        result = subprocess.run([str(BACKEND), "ipre_action_run"], env=self.env, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = result.stdout.splitlines()
        self.assertEqual(len(rows), len(names) + 2)
        for row in rows:
            self.assertEqual(row.count(b"\t"), 1)
            self.assertNotIn(b"\x1b", row)
        keys = [row.split(b"\t", 1)[0].decode() for row in rows]
        self.assertIn(path_key(raw_path), keys)
        result = self.backend("ipre_action_copy", "--encoded", *keys)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state / "CLIP").read_text().splitlines(), ["COPY", *keys])
        self.backend("ipre_action_right", str(destination))
        result = self.backend("ipre_action_paste")
        self.assertEqual(result.returncode, 0, result.stderr)
        for i, name in enumerate(names):
            self.assertEqual((destination / name).read_text(), str(i))
        with open(os.fsencode(destination) + b"/" + raw_name, "rb") as file:
            self.assertEqual(file.read(), b"raw bytes")
        self.assertTrue((destination / broken.name).is_symlink())
        self.assertEqual(os.readlink(destination / broken.name), "missing")

        self.backend("ipre_action_cut", "--encoded", *keys)
        result = self.backend("ipre_action_paste")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state / "CLIP").read_text(), "")
        self.assertFalse(any(self.cwd.iterdir()))
        self.assertEqual((destination / "tail\n_copy1").read_text(), "3")

    def test_record_copy_does_not_overwrite_dangling_symlink(self):
        source = self.cwd / "a -> b%.txt"
        source.write_text("payload")
        target_dir = self.root / "destination"
        target_dir.mkdir()
        link = target_dir / source.name
        link.symlink_to("missing")
        encoded = path_key(source)
        record = encoded + "\ta -> b%.txt"
        self.assertEqual(self.backend("ipre_action_copy", "--records", record).returncode, 0)
        (self.state / "CWD").write_text(path_key(target_dir) + "\n")
        result = self.backend("ipre_action_paste")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), "missing")
        self.assertEqual((target_dir / "a -> b%_copy1.txt").read_text(), "payload")

    def test_failed_cut_preserves_buffer(self):
        source = self.root / "payload"
        source.write_text("payload")
        (self.state / "CWD").write_text(path_key(self.root / "missing") + "\n")
        (self.state / "CLIP").write_text(f"CUT\n{source}\n")
        result = self.backend("ipre_action_paste")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(source.exists())
        self.assertEqual((self.state / "CLIP").read_text(), f"CUT\n{source}\n")
        self.assertFalse((self.state / "FOCUS").exists())
        self.assertEqual((self.state / "NOTICE").read_text().strip(), "Paste: 1 failed")

    def test_paste_failure_after_navigation_into_readonly_directory(self):
        if os.geteuid() == 0:
            self.skipTest("root bypasses directory write permissions")
        source_dir = self.cwd / "source"
        source_dir.mkdir()
        source = source_dir / "report.txt"
        source.write_text("payload")
        destination = self.cwd / "destination"
        destination.mkdir()
        destination.chmod(0o555)
        self.addCleanup(destination.chmod, 0o755)

        for action in ("cut", "copy"):
            with self.subTest(action=action):
                (self.state / "CWD").write_text(path_key(self.cwd) + "\n")
                self.backend("ipre_action_right", "source")
                self.backend(f"ipre_action_{action}", "report.txt")
                clipboard = (self.state / "CLIP").read_text()
                self.backend("ipre_action_left")
                self.backend("ipre_action_right", "destination")
                self.assertEqual((self.state / "CWD").read_text().strip(), path_key(destination))

                result = self.backend("ipre_action_paste")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Permission denied", result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(source.read_text(), "payload")
                self.assertEqual(list(destination.iterdir()), [])
                self.assertEqual((self.state / "CLIP").read_text(), clipboard)
                self.assertFalse((self.state / "FOCUS").exists())
                header = self.backend("ipre_action_header_info")
                self.assertIn("Paste: 1 failed", header.stdout)

    def test_paste_directory_into_itself_or_descendant_is_rejected_before_copying(self):
        source = self.cwd / "bundle"
        source.mkdir()
        (source / "report.txt").write_text("payload")
        child = source / "child"
        child.mkdir()
        alias = self.cwd / "alias"
        alias.symlink_to(child, target_is_directory=True)

        for action in ("copy", "cut"):
            for steps, destination in [
                (("bundle",), source),
                (("bundle", "child"), child),
                (("alias",), alias),
            ]:
                with self.subTest(action=action, steps=steps):
                    (self.state / "CWD").write_text(path_key(self.cwd) + "\n")
                    self.backend(f"ipre_action_{action}", "bundle")
                    clipboard = (self.state / "CLIP").read_text()
                    for step in steps:
                        self.backend("ipre_action_right", step)

                    result = self.backend("ipre_action_paste")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("cannot place a directory inside itself", result.stderr)
                    self.assertEqual(result.stdout, "")
                    self.assertFalse((destination / "bundle").exists())
                    self.assertEqual((source / "report.txt").read_text(), "payload")
                    self.assertEqual((self.state / "CLIP").read_text(), clipboard)
                    self.assertFalse((self.state / "FOCUS").exists())
                    self.assertEqual((self.state / "NOTICE").read_text(), "Paste: 1 failed\n")

    def test_paste_partial_cut_retains_failed_items_and_can_retry(self):
        if os.geteuid() == 0:
            self.skipTest("root bypasses directory write permissions")
        protected = self.cwd / "protected"
        protected.mkdir()
        failed = protected / "failed.txt"
        failed.write_text("failed payload")
        good = self.cwd / "good.txt"
        good.write_text("good payload")
        destination = self.cwd / "destination"
        destination.mkdir()
        self.backend("ipre_action_cut", "protected/failed.txt", "good.txt")
        self.backend("ipre_action_right", "destination")
        protected.chmod(0o555)
        self.addCleanup(protected.chmod, 0o755)

        result = self.backend("ipre_action_paste")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Permission denied", result.stderr)
        self.assertEqual(failed.read_text(), "failed payload")
        self.assertFalse(good.exists())
        self.assertEqual((destination / "good.txt").read_text(), "good payload")
        self.assertEqual((self.state / "CLIP").read_text(), f"CUT\n{failed}\n")
        self.assertEqual((self.state / "FOCUS").read_text(), path_key(destination / "good.txt") + "\n")
        self.assertEqual((self.state / "NOTICE").read_text(), "Paste: 1 failed\n")

        protected.chmod(0o755)
        result = self.backend("ipre_action_paste")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(failed.exists())
        self.assertEqual((destination / "failed.txt").read_text(), "failed payload")
        self.assertEqual((self.state / "CLIP").read_text(), "")
        self.assertEqual((self.state / "FOCUS").read_text(), path_key(destination / "failed.txt") + "\n")
        self.assertEqual((self.state / "NOTICE").read_text(), "")
        self.assertEqual(sorted(p.name for p in destination.iterdir()), ["failed.txt", "good.txt"])

    def test_paste_partial_copy_focuses_success_and_keeps_copy_buffer(self):
        if os.geteuid() == 0:
            self.skipTest("root bypasses file read permissions")
        failed = self.cwd / "failed.txt"
        failed.write_text("failed payload")
        good = self.cwd / "good.txt"
        good.write_text("good payload")
        destination = self.cwd / "destination"
        destination.mkdir()
        self.backend("ipre_action_copy", "failed.txt", "good.txt")
        clipboard = (self.state / "CLIP").read_text()
        self.backend("ipre_action_right", "destination")
        failed.chmod(0o000)
        self.addCleanup(failed.chmod, 0o644)

        result = self.backend("ipre_action_paste")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Permission denied", result.stderr)
        self.assertFalse((destination / "failed.txt").exists())
        self.assertEqual((destination / "good.txt").read_text(), "good payload")
        self.assertTrue(good.exists())
        self.assertEqual((self.state / "CLIP").read_text(), clipboard)
        self.assertEqual((self.state / "FOCUS").read_text(), path_key(destination / "good.txt") + "\n")
        self.assertEqual((self.state / "NOTICE").read_text(), "Paste: 1 failed\n")

    def test_paste_failed_directory_copy_does_not_focus_partial_destination(self):
        if os.geteuid() == 0:
            self.skipTest("root bypasses file read permissions")
        source = self.cwd / "bundle"
        source.mkdir()
        (source / "good.txt").write_text("good payload")
        unreadable = source / "unreadable.txt"
        unreadable.write_text("unreadable payload")
        destination = self.cwd / "destination"
        destination.mkdir()
        self.backend("ipre_action_copy", "bundle")
        clipboard = (self.state / "CLIP").read_text()
        self.backend("ipre_action_right", "destination")
        unreadable.chmod(0o000)
        self.addCleanup(unreadable.chmod, 0o644)

        result = self.backend("ipre_action_paste")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Permission denied", result.stderr)
        self.assertEqual((destination / "bundle/good.txt").read_text(), "good payload")
        self.assertFalse((destination / "bundle/unreadable.txt").exists())
        self.assertEqual((self.state / "CLIP").read_text(), clipboard)
        self.assertFalse((self.state / "FOCUS").exists())
        self.assertEqual((self.state / "NOTICE").read_text(), "Paste: 1 failed\n")

    def test_paste_success_avoids_dangling_symlink_conflicts(self):
        for action in ("copy", "cut"):
            with self.subTest(action=action):
                source = self.cwd / f"{action}.txt"
                source.write_text("payload")
                destination = self.cwd / action
                destination.mkdir()
                link = destination / source.name
                link.symlink_to("missing")
                next_link = destination / f"{action}_copy1.txt"
                next_link.symlink_to("also-missing")
                (self.state / "CWD").write_text(path_key(self.cwd) + "\n")
                (self.state / "NOTICE").write_text("Paste: 1 failed\n")
                self.backend(f"ipre_action_{action}", source.name)
                self.assertEqual((self.state / "NOTICE").read_text(), "")
                clipboard = (self.state / "CLIP").read_text()
                self.backend("ipre_action_right", action)

                result = self.backend("ipre_action_paste")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(os.readlink(link), "missing")
                self.assertEqual(os.readlink(next_link), "also-missing")
                self.assertEqual((destination / f"{action}_copy2.txt").read_text(), "payload")
                self.assertEqual(source.exists(), action == "copy")
                self.assertEqual((self.state / "CLIP").read_text(), clipboard if action == "copy" else "")
                self.assertEqual((self.state / "FOCUS").read_text(), path_key(destination / f"{action}_copy2.txt") + "\n")
                self.assertEqual((self.state / "NOTICE").read_text(), "")

    def test_paste_cut_into_same_parent_via_alias_is_a_noop(self):
        source = self.cwd / "report.txt"
        source.write_text("payload")
        alias = self.root / "alias"
        alias.symlink_to(self.cwd, target_is_directory=True)
        self.backend("ipre_action_cut", "report.txt")
        self.backend("ipre_action_right", str(alias))

        result = self.backend("ipre_action_paste")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(source.read_text(), "payload")
        self.assertEqual(list(self.cwd.iterdir()), [source])
        self.assertEqual((self.state / "CLIP").read_text(), "")
        self.assertFalse((self.state / "FOCUS").exists())
