## Examples

Basic Example:
![](./ipre_example_basic.gif)

Advanced Example:
![](./ipre_example_advanced.gif)


## Dependency
The following programs are required by the `pre` command:

1. `chafa`    - print image in terminal(the kernel)
2. `eza`      - preview directory
3. `bat`      - preview text/source files
4. `pdftoppm` - preview pdf files
5. `ddjvu`    - preview djvu files
6. `magick`   - preview fonts
7. `ffmpegthumbnailer`      - preview videos
8. `archivemount/fuse-zip`  - preview tar(.gz) or zip files
9. `gnome-epub-thumbnailer` - preview EPub or MOBI books

To make `chafa` work, your terminal must support the `sixel` protocol, and your shell must be `Zsh`.


## Usage
Add this script to your `PATH`.

## basic
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

## Config
Configure this program by environment variables. 

* set `EZA_ARG` to change the default argument of `eza`;
* set `FONT_TEXT` to change the sample text in font-preview.

## play with shell
Add the scripts - `pre`, `ipre` and `ipre_backend` to your PATH, and then add the following config to your `.zshrc`:

```shell
# inline (file) preview in shell
function ipre() {
    local tmp="$(mktemp -t "ipre-cwd.XXXXXX")" cwd
    command ipre "$@" --cwd-file="$tmp"
    cwd="$(cat -- "$tmp" 2>/dev/null)"
    [ -n "$cwd" ] && [ "$cwd" != "$PWD" ] && builtin cd -- "$cwd"
    rm -f -- "$tmp"
}

# NOTE: function 'yy' do NOT support infinite depth
function yy() {
    local tmp="$(mktemp -t "ipre-cwd.XXXXXX")" cwd
    command ipre "$@" --cwd-file="$tmp" --max-depth 1
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
9. zshell / bash builtin

Using examples:

```shell
ipre                      # search current directory
ipre <dir>                # search dir
ipre <dir_1> ... <dir_n>  # search all of these directories together 

# add more filter to fd
ipre -e c <dir>           # select files with extension '.c'
ipre <dir> --maxdepth 1   # perform likes yazi
```

Keybinds:

```txt
=== ipre Keybindings ===
  Enter              : Open file/directory
  Left/Right         : Navigate parent/child directories
  `(Backtick)        : Toggle File/Directory/All view
  Alt+p              : Toggle preview window
  Alt+.              : Toggle hidden files
  Alt+0~9            : Set search depth (0 for infinite)
  Alt+-/=            : Decrease/Increase search depth
  Alt+o              : Cycle sort mode (name/time/size/ext)
  Alt+g              : Live Grep (Search file content)
  Alt+a              : Toggle selection (Invert)
  Alt+y              : Copy path(s) to clipboard
  Alt+c/x/v          : Copy/Cut/Paste files
  Alt+i              : Inspect ipre clipboard
  Alt+w              : Clear ipre clipboard
  Alt+r              : Rename selected item(s)
  Alt+e              : Wdired batch rename
  Alt+n              : Create new file/directory
  Alt+d              : Delete selected
  Alt+s              : Bookmark selected items
  Alt+b              : Open bookmarks menu
  Alt+?              : Show this help
  Alt+q              : Exit and CD to current viewed dir
```


Notes:

* set `IPRE_FD` to change the default search method;
* set `EDITOR` to change the default text file opener command;
* you may need to replace `wl-copy` with your own clipboard program;
* to use `live grep`(alt-g), you need to install `ripgrep`.

## WARNING

* if pdf-preview does NOT work, clean the folder `~/.cache/pre_thumbs`.
* before clear the cache folder `~/.cache/pre_thumbs`, run `umount ~/.cache/pre_thumbs/mnt` first !!!
