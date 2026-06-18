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
```

To use this function, install the following:

1. `fd/fzf`   - the kernel
2. `imv`      - open image
3. `zathura`  - open pdf
4. `nvim`     - the text editor

Using examples:

```shell
ipre                      # search current directory
ipre <dir>                # search dir
ipre <dir_1> ... <dir_n>  # search all of these directories together 
```

Notes:

* set `IPRE_FD` to change the default search method;
* set `EDITOR` to change the default text file opener command;
* you may need to replace `wl-copy` with your own clipboard program;

## WARNING

* if pdf-preview does NOT work, clean the folder `~/.cache/pre_thumbs`.
* before clear the cache folder `~/.cache/pre_thumbs`, run `umount ~/.cache/pre_thumbs/mnt` first !!!
