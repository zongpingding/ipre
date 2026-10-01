## Examples

Basic Example:
![](./examples/ipre_example_basic.gif)

Advanced Example:
![](./examples/ipre_example_advanced.gif)

NOTE: these GIFs might be out of date.

## WARN
To use these scripts, you MUST use `zshell`.

## Dependency
The following programs are required by the `pre` command:

1. `chafa`    - print image in terminal(the kernel)
2. `eza`      - preview directory
3. `bat`      - preview text/source files
4. `pdftoppm` - preview pdf files(`pdfinfo` for page counting)
5. `ddjvu`    - preview djvu files(`djvused` for page counting)
6. `magick`   - preview fonts
7. `ffmpegthumbnailer`      - preview videos
8. `archivemount/fuse-zip`  - preview tar(.gz) or zip files
9. `gnome-epub-thumbnailer` - preview EPub or MOBI books

NOTE: For `chafa` to work, your terminal may need to support the `sixel` protocol.

## Usage
Add this script to your `PATH`.

## Basic
Provide a filename as an argument like this:
```shell
# view page 1 in test.pdf
$ pre test.pdf
# view page 4 in test.pdf/test.djvu
$ pre test.pdf 4
$ pre test.djvu 4

$ pre test.mp4
$ pre test.png
$ pre times.ttf
$ pre test.epub
```

Each `ipre` invocation keeps its own navigation, selection, and clipboard state.
Bookmarks and the trash bin are shared between invocations.
Each deleted item keeps its original name in the `payload/` subdirectory of a
separate, atomically created `entry-<timestamp>.<random>` trash entry. The entry's
`origin` file records the original absolute path, terminated by a NUL byte.
Same-named items can be deleted together or from concurrent sessions without
replacing one another. Restore returns items to their original directories,
recreates missing parent directories, and adds `_restoredN` to names that already
exist there. The restore menu displays each item's original path.
The default listing depth is 1 (the current directory's immediate children).
Use `--depth N` or `Alt+1` through `Alt+9` to change it. `Alt+0` or
`--depth 0` searches without a depth limit and displays matches as they arrive;
that mode does not apply the selected sort order or eza icons.

When renaming, the prompt contains only the selected item's name. The edited
name is relative to that item's parent directory. For example, renaming
`/a/b/c/d.txt` to `d_modify.txt` yields `/a/b/c/d_modify.txt`; entering
`../d_modify.txt` moves it to `/a/b/d_modify.txt`. Batch rename uses the same rule.
Each batch rename row has a fixed `[id]`, a TAB and the editable new name.
Source paths are shown in comments and kept separately in memory.
Rename a directory and its children in separate batches. Batch moves
use temporary paths beside each source and attempt to restore the original
paths if a move fails.
Paths are stored with reversible byte-level percent encoding, independently of
icons and displayed names. Names containing ` -> `, TAB, newlines, percent signs
and non-UTF-8 bytes can be selected and operated on without losing their paths.
Name editors display `\n` for newline, `\t` for TAB and `\\` for a literal
backslash. See [PATH_PROTOCOL.md](./PATH_PROTOCOL.md) for the record/state format.
Legacy bookmarks are migrated to `bookmarks.paths-v1` on first use.

Paste focuses the first successfully copied or moved item. Failed cut items stay
in the clipboard for retry; successful moves are removed from it. Copy keeps its
clipboard. Failures appear as `Paste: N failed` in the header. Pasting a directory
into itself or one of its descendants is rejected before copying or moving it,
including destinations reached through directory symlinks.
A copy that fails partway through may leave partially copied files at the
destination; it is reported as a failure and does not become the focus target.

## Config
Configure this program by environment variables. 

* set `EZA_ARG` to change the default argument of `eza`;
* set `FONT_TEXT` to change the sample text in font-preview.

## Play with (z)shell
Keep `pre`, `ipre`, `ipre_backend`, `ipre_palette` and `ipre_paths` together in a
directory on your PATH, and then add the following config to your `.zshrc`:

```shell
# inline (file) preview in shell
function ipre() {
    local tmp="$(mktemp -t "ipre-cwd.XXXXXX")" cwd
    command ipre "$@" --cwd-file="$tmp"
    cwd="$(cat -- "$tmp" 2>/dev/null)"
    [ -n "$cwd" ] && [ "$cwd" != "$PWD" ] && builtin cd -- "$cwd"
    rm -f -- "$tmp"
}
# '--no-leave' argument will break directory changing of RET.
function yy() {
    local tmp="$(mktemp -t "ipre-cwd.XXXXXX")" cwd
    command ipre "$@" --cwd-file="$tmp" --depth 1
    cwd="$(cat -- "$tmp" 2>/dev/null)"
    [ -n "$cwd" ] && [ "$cwd" != "$PWD" ] && builtin cd -- "$cwd"
    rm -f -- "$tmp"
}
```

This function depends on the following stuff:

1. `fd/fzf`   - the kernel
2. `du`       - show file size
3. `imv`      - open image
4. `zathura`  - open pdf
5. `nvim`     - the text editor
6. `wl-copy`  - clipboard support
7. `awk/sed/grep` - as it is
8. `tr/cut/wc/head/tail` - as it is
9. `ripgrep/ast-grep` - better grep
10. zshell / bash builtin

Using examples:

```shell
ipre                      # search current directory
ipre <dir>                # search dir
ipre <dir_1> ... <dir_n>  # search all of these directories together 

# add more filter to fd
ipre -e c <dir>           # select files with extension '.c'
ipre <dir> --depth 1      # list immediate children (also the default)
```

Keybinds:

```txt
=== ipre Keybindings ===
  Ctrl+q             : Exit ipre
  Alt+q              : Exit and CD to current viewed dir
  Enter              : Open file/directory
  [Left/Right]       : Navigate parent/child directories
  Alt+[f/b]          : Preview window Scroll down/up
  `(Backtick)        : Toggle File/Directory/All view
  Alt+p              : Toggle preview window
  Alt+.              : Toggle hidden files
  Alt+[0~9]          : Set search depth (0 for infinite)
  Alt+[-/=]          : Decrease/Increase search depth
  Alt+o              : Cycle sort mode (name/time/size/ext)
  Alt+g              : Live Grep (Search file content)
  Alt+a              : Toggle selection (Invert)
  Alt+y              : Copy path(s) to clipboard
  Alt+[c/x/v]        : Copy/Cut/Paste files
  Alt+i              : Inspect ipre select|clip system
  Alt+s              : Cross-directory multi-selection
  Alt+r              : Rename selected item(s) |Use Ripgrep in live grep
  Alt+f              : Preview window Scroll up|Use Fuzzy in live grep
  Alt+w              : Wdired batch rename(UNSAFE)
  Alt+n              : Create new file/directory
  Alt+d              : Delete selected
  Alt+m              : Bookmark selected items
  Alt+/              : Open bookmarks menu
  Alt+;              : Global Search & Replace[rg](by nvim & grug-far.nvim)
  Alt+'              : Global Search & Replace[ast-rg](by nvim & grug-far.nvim)
  Alt+?              : Show this help
  Alt+t              : To directory by Zoxide
  Alt+Space          : Open command pallete
```

Notes:

* set `IPRE_FD` to change the default search method;
* set `EDITOR` to change the default text file opener command;
* set `CLIPBOARD` to change the default clipboard program;
* to use `live grep`(`alt-g`), you need to install `ripgrep`.
* to use `global search & replace`(`alt-;` or `alt-'`), you need to install `ripgrep` and `ast-grep`.

For example, add `.git` filter to `IPRE_FD`:

```shell
export IPRE_FD='fd --follow -I . -E .git'
```

## WARNING

* if pdf-preview does NOT work, clean the folder `~/.cache/pre_thumbs`.
* before clearing `~/.cache/pre_thumbs`, unmount any remaining `mnt.*` directories from interrupted archive previews.

## Tests

```shell
python3 tests/run.py
```

This checks shell syntax and runs the regression suites, including real fzf
interaction and concurrent-session isolation. To run one area, use
`python3 tests/run.py -k cache`. Dependencies, coverage and test isolation are
documented in [tests/README.md](./tests/README.md).

Preview thumbnails use the absolute source path, nanosecond timestamps, file
identity and rendering options as their cache key. `pre` honors `XDG_CACHE_HOME`
(or `IPRE_CACHE_DIR` when launched by ipre); old thumbnails need no migration.
