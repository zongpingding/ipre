## Example

![](./ipre_example.gif)

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

## play with fzf
Add the following script to your `.zshrc`:

```shell
# change the path
source /path/to/ipre.zsh

# create an alias which similar to yazi
alias yy='ipre --max-depth 1'
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

- basic:

  1. `Tab`: toggle entry selection
  2. `` ` ``: switch entry list mode: `all`, `file`, and `directory`
  3. `Left`: go to the parent directory
  4. `Right`: enter the selected directory

- copy/cut/paste/delete:

  1. `Alt-X`: cut selected files/directories
  2. `Alt-C`: copy selected files/directories
  3. `Alt-V`: paste files/directories
  4. `Alt-R`: delete selected files/directories

- misc:

  1. `Alt-.`: toggle hidden files
  2. `Alt-P`: toggle preview window
  3. `Alt-A`: copy all entries to the clipboard
  4. `Alt-Y`: copy the current entry to the clipboard


Notes:

* set `IPRE_FD` to change the default search method;
* set `EDITOR` to change the default text file opener command;
* you may need to replace `wl-copy` with your own clipboard program;

## WARNING

* if pdf-preview does NOT work, clean the folder `~/.cache/pre_thumbs`.
* before clear the cache folder `~/.cache/pre_thumbs`, run `umount ~/.cache/pre_thumbs/mnt` first !!!
