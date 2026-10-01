"""Directory visits form per-session back/forward stacks."""

from support import IpreTestCase, path_key


class HistoryTests(IpreTestCase):
    def visit(self, folder):
        result = self.backend("ipre_action_right", "--encoded", path_key(folder))
        self.assertEqual(result.returncode, 0, result.stderr)

    def jump(self, direction, folder):
        result = self.backend("ipre_action_history_" + direction)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state / "CWD").read_text(), path_key(folder) + "\n")

    def test_back_forward_and_branching_keep_literal_paths(self):
        first = self.cwd / "first -> %0A\n"
        second = first / "second\t"
        third = self.cwd / "third"
        second.mkdir(parents=True)
        third.mkdir()
        self.visit(first)
        self.visit(second)
        self.jump("back", first)
        self.jump("back", self.cwd)
        self.jump("back", self.cwd)
        self.jump("forward", first)
        forward = (self.state / "FORWARD").read_text()
        self.visit(first)
        self.assertEqual((self.state / "FORWARD").read_text(), forward)
        self.jump("forward", second)
        self.jump("back", first)
        self.visit(third)
        self.assertEqual((self.state / "FORWARD").read_text(), "")
        self.jump("forward", third)
        self.jump("back", first)

    def test_unavailable_history_entries_are_skipped(self):
        deleted = self.cwd / "deleted"
        other = self.cwd / "other"
        deleted.mkdir()
        other.mkdir()
        self.visit(deleted)
        self.visit(other)
        deleted.rmdir()
        self.jump("back", self.cwd)
        self.assertEqual((self.state / "BACK").read_text(), "")
        self.jump("forward", other)

    def test_parent_and_bookmark_navigation_record_visits(self):
        folder = self.cwd / "nested"
        folder.mkdir()
        self.visit(folder)
        result = self.backend("ipre_action_left")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.jump("back", folder)
        (self.state / "BOOKMARKS").write_text(path_key(self.cwd) + "\n")
        result = self.backend("ipre_action_open_bookmarks",
                              script='fzf() { cat; }; source "$1" "$2"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state / "FORWARD").read_text(), "")
        self.jump("back", folder)

    def test_history_keeps_clipboard_and_selection_and_clears_search_roots(self):
        folder = self.cwd / "nested"
        folder.mkdir()
        source = self.cwd / "source.txt"
        source.write_text("payload")
        self.backend("ipre_action_copy", "--encoded", path_key(source))
        self.backend("ipre_action_mark", "--encoded", path_key(source))
        self.visit(folder)
        (self.state / "TARGETS").write_text(path_key(folder) + "\n")
        (self.state / "STATE").write_text("file\n")
        self.jump("back", self.cwd)
        self.assertEqual((self.state / "STATE").read_text(), "all\n")
        self.assertEqual((self.state / "TARGETS").read_text(), "")
        self.assertEqual((self.state / "CLIP").read_text(), f"COPY\n{path_key(source)}\n")
        self.assertEqual((self.state / "SELECT").read_text(), path_key(source) + "\n")
