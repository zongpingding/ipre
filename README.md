# Example

![](./ipre_example.gif)

# Dependency

My terminal - `foot`, shell - `zsh`.

1. fd/fzf   - the kernel
2. imv      - view image
3. zathura  - view pdf
4. nvim     - text editor

The following items are required by the 'pre' command:

1. chafa    - preview image in terminal
2. eza      - preview directory structure
3. tree     - preview zip/tar structure
4. pdftoppm - convert pdf to PNG-format image
4. bat      - preview text/source files
6. ffmpegthumbnailer - video thumbnailer preview

Usage:

* set `IPRE_CMD` to change the default search method;
* set `EDITOR` to change the default text file opener command;
* if pdf-preview does NOT working, clean the folder `~/.cache/pre_thumbs`

# Usage
Add this script to your `PATH`.

## basic
Provide a filename as an argument like this:
```shell
$ pre test.pdf
$ pre test.mp4
$ pre test.png
```

## play with fzf
Add the following script to your `~/.zshrc`:

```shell
function ipre() {
    local cmd file
    if [[ -n "$IPRE_CMD" ]]; then
        cmd=(${=IPRE_CMD})
    else
        cmd=(
            fd . --hidden --follow
            -E .git
            -E target
            -E .cargo
            -E build
            -E .npm
            -E node_modules
            -E .cache
            -E dist
            -E out
            -E lsp-bridge
            # other ignore dir
            -E .java
            -E .gradle
            -E .nuget
            -E .steam
            -E .android
            -E .ipython
            -E .vscode
            -E .vscode-oss
            -E .oh-my-zsh
            -E .emacs-tmp
            -E .pub-cache
            -E .proxyman
            )
    fi
    if [[ $# -gt 0 ]]; then
        cmd+=("$@")
    fi
    # file select and preview
    file=$(
        "${cmd[@]}" | fzf \
        --preview 'pre {}' \
        --height=50% --reverse  \
        --preview-window=right:60%
        )
    # post action for selection:
    [[ -z "$file" ]] && return
    if [[ -d "$file" ]]; then
        cd "$file"
        return
    fi
    case "${file:l}" in
        *.png|*.jpg|*.jpeg|*.gif|*.webp|*.bmp|*.tiff)
            nohup imv "$file" &>/dev/null &
            ;;
        *.pdf)
            nohup zathura "$file" &>/dev/null &
            ;;
        *.tar|*.tar.gz|*.tgz|*.tar.xz|*.txz|*.tar.bz2|*.tbz2)
            return
            ;;
        *.zip)
            return
            ;;
        # for text files to open:
        *)
            ${EDITOR:-nvim} "$file"
            ;;
    esac
}
```
