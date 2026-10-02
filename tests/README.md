# Regression tests

Run the complete check from any directory:

```sh
python3 /path/to/ipre/tests/run.py
```

From the repository root:

```sh
python3 tests/run.py
python3 tests/run.py -k cache
python3 tests/run.py -p test_palette.py
```

The runner checks dependencies and all five zsh scripts' syntax before running
the tests. It exits nonzero on a syntax error, missing dependency or test failure.
Standard discovery also works: `python3 -m unittest discover -s tests -v`.

## Environment

Use Linux, Python 3 and zsh, with bash, fd, fzf, ripgrep, file and GNU coreutils
installed. No Python packages, editor, graphical display or PDF renderer are
required. fzf must support `--id-nth` and `reload-sync` for view changes that retain
selection. Run as a regular user: tests of directory write permissions are skipped
as root. Some tests require a working PTY; run outside containers that prohibit
PTY creation. Individual suites may skip tests when fd/fzf/rg are unavailable;
the full runner requires these tools. Check the summary for skipped tests.

Each test uses a temporary directory for data, XDG locations and session state.
Inherited `IPRE_*` and `FZF_*` settings are excluded. Tests do not change `HOME`
or use the user's files, bookmarks or trash. PTY tests answer terminal cursor
queries and send keyboard input automatically. Files in `ipre_live_test/` are
manual fixtures and are neither used nor removed by this suite.

## Coverage

| Suite | Checks |
| --- | --- |
| `test_browser.py` | Listing, navigation, depth parsing, frontend selection, real fzf keys/reload |
| `test_history.py` | Back/forward, new visits, deleted directories, bookmark visits and buffer preservation |
| `test_details.py` | Aligned attributes in real fzf, Unicode names, large sizes, filename-only search and operation identity |
| `test_open.py` | Shared Enter/palette dispatch, mixed types, extensionless MIME detection, custom argv and cancellation |
| `test_sessions.py` | Two simultaneous frontends, independent state, cleanup while the other stays open |
| `test_paths.py` | Byte-preserving encoding, invalid input, stream boundaries |
| `test_buffers.py` | Bookmarks, selection and buffer editing |
| `test_rename.py` | Source identity, swaps, conflicts, staging and rollback |
| `test_wdired.py` | Row validation/cancellation/CRLF, special byte names, aliases, mixed-type cycles, hardlinks/FIFOs/sockets, permissions, directory replacement, signals, staging/commit failures and recovery |
| `test_paste.py` | Copy/cut success, partial failure, retries, self/descendant guards |
| `test_trash.py` | Collision-free deletion, original-path restoration, failure preservation, screen cleanup |
| `test_preview.py` | Preview arguments, PDF/DjVu page limits, text scrolling and grep paths |
| `test_cache.py` | Actual `pre` entry point, directory identity, cache reuse, timestamp precision and pages |
| `test_palette.py` | Cancel/empty prompts, real Ctrl+C, execution modes and alternate-screen cleanup |
| `test_palette_files.py` | Symlink conflicts, exact clipboard bytes, internal command history and safe selected-file arguments |
| `test_preview_geometry.py` | Preview size limits and real frontend F4/F5/F6 sizing and layout changes |

The cache suite replaces PDF rendering and image display with deterministic
commands while running `pre` itself. The concurrency test holds two real
frontends open with a controlled fzf replacement; other tests exercise real fzf.
Injected move/copy failures let tests verify that original data and retry state
survive failures without relying on timing or hardware faults.
Wdired tests inject failure before and after each of the six moves in a
three-item cycle. They also replace paths during editing, staging, commit and
rollback, checking that unrelated files survive and recovery maps are retained
when automatic restoration cannot finish. Cross-filesystem rejection is tested
with a simulated device ID; socket tests require permission to bind a local
Unix socket in the temporary directory.
The browser interaction test sends real `Alt+e`, `F2` and `F3` keys and checks
that multi-selection survives the switch to detailed view and filename search
survives switching back and forth. Opener tests record
arguments with temporary mock applications; they do not launch desktop apps.

When fixing a bug, add a regression to the relevant suite. Prefer observable
files, state, command arguments and terminal output over assertions about source
text. `support.py` contains fixtures and helpers only, with no tests of its own.
