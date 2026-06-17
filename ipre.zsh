# inline (file) preview in zshell

# NOTE: 1. variables '$2' and '$3' can(may) be used to reprensent
#          the width and height of the preview window.
#       2. maybe we can replace chafa by imgcat, which is faster.
#       3. 'transform-prompt' does NOT evaluate danymiclly.
#       4. maybe we can use 'skim' - just like fzf but in Rust.
function ipre() {
    local cmd cmd_str FZF_STATE_FILE FZF_CWD_FILE
    if [[ -n "$IPRE_LS" ]]; then
        cmd=(${=IPRE_LS})
    else
        cmd=(
            fd --hidden --follow
            -E .git -E target -E .cargo -E build -E .npm -E node_modules
            -E .cache -E dist -E out -E lsp-bridge
            -E .java -E .gradle -E .nuget -E .steam -E .android
            -E .ipython -E .vscode -E .vscode-oss -E .oh-my-zsh
            -E .emacs-tmp -E .pub-cache -E .proxyman
            . # search all patterns
        )
    fi
    if [[ $# -gt 0 ]]; then
        cmd+=("$@")
    fi

    # safely escape the base command array into a string
    cmd_str=$(printf '%q ' "${cmd[@]}")

    # Initialize State Files for FZF isolated environment
    mkdir -p "$HOME/.cache/pre_thumbs"
    FZF_STATE_FILE="$HOME/.cache/pre_thumbs/fzf_state"
    FZF_CWD_FILE="$HOME/.cache/pre_thumbs/fzf_cwd"
    
    echo "file" > "$FZF_STATE_FILE"
    echo "$PWD" > "$FZF_CWD_FILE"

    # Core Generator: Always change dir to current browsing state first, then run fd
    # Note: Use subshell '( ... )' to avoid polluting the host shell's PWD.
    local get_list="( \
        cd \"\$(cat '$FZF_CWD_FILE')\" && \
        if grep -qxF 'directory' '$FZF_STATE_FILE'; then \
            eval \"$cmd_str --type d\"; \
        elif grep -qxF 'all' '$FZF_STATE_FILE'; then \
            eval \"$cmd_str\"; \
        else \
            eval \"$cmd_str --type f\"; \
        fi \
    )"

    # Fzf Bindings
    local bind_switch="\`:reload( \
        if grep -qxF 'file' '$FZF_STATE_FILE'; then \
            echo 'directory' > '$FZF_STATE_FILE'; \
        elif grep -qxF 'directory' '$FZF_STATE_FILE'; then \
            echo 'all' > '$FZF_STATE_FILE'; \
        else \
            echo 'file' > '$FZF_STATE_FILE'; \
        fi; \
        eval \"$get_list\" \
    )"

    local bind_right="right:reload( \
        cur=\"\$(cat '$FZF_CWD_FILE')\"; \
        cd \"\$cur\"; \
        if [ -d {} ]; then \
            new=\"\$(realpath {})\"; \
        else \
            new=\"\$(realpath \"\$(dirname {})\")\"; \
        fi; \
        echo \"\$new\" > '$FZF_CWD_FILE'; \
        eval \"$get_list\" \
    )"

    local bind_left="left:reload( \
        cur=\"\$(cat '$FZF_CWD_FILE')\"; \
        new=\"\$(realpath \"\$cur/..\")\"; \
        echo \"\$new\" > '$FZF_CWD_FILE'; \
        eval \"$get_list\" \
    )"

    # Execute Fzf
    local -a selected_items
    selected_items=("${(@f)$(
        eval "$get_list" | fzf \
        --multi \
        --prompt "ipre > " \
        --preview "cd \"\$(cat '$FZF_CWD_FILE')\" && printf '\033[2J\033[H'; pre {}" \
        --height=50% --reverse \
        --preview-window=right:60% \
        --bind 'resize:refresh-preview' \
        --bind "focus,load:transform-header:cd \"\$(cat '$FZF_CWD_FILE')\" && (file --brief {} 2>/dev/null || echo 'No file')" \
        --bind "$bind_switch" \
        --bind 'alt-p:toggle-preview' \
        --bind 'alt-a:select-all' \
        --bind "alt-a:+execute-silent(cd \"\$(cat '$FZF_CWD_FILE')\" && realpath {+} | wl-copy)" \
        --bind "alt-y:execute-silent(cd \"\$(cat '$FZF_CWD_FILE')\" && realpath {} | wl-copy)" \
        --bind "alt-r:execute-silent(cd \"\$(cat '$FZF_CWD_FILE')\" && rm -rf {}) + reload(eval \"$get_list\")" \
        --bind "$bind_left" \
        --bind "$bind_right"
    )}")

    # Post action for selection:
    if [[ ${#selected_items[@]} -eq 0 || -z "${selected_items[1]}" ]]; then
        return
    fi

    # Read the final navigated directory
    local final_cwd="$(cat "$FZF_CWD_FILE")"

    # Map output (which are now clean, relative filenames) to absolute paths
    local -a abs_items
    for item in "${selected_items[@]}"; do
        abs_items+=("$final_cwd/$item")
    done
    local first_file="${abs_items[1]}"

    # If only one item is selected and it's a directory, change directory into it
    if [[ ${#abs_items[@]} -eq 1 && -d "$first_file" ]]; then
        cd "$first_file"
        return
    fi
    local ext="${first_file:l:e}"
    case "$ext" in
        png|jpg|jpeg|gif|webp|bmp|tiff)
            imv "${abs_items[@]}" &>/dev/null &!
            ;;
        pdf|djvu|epub|mobi)
            zathura "${abs_items[@]}" &>/dev/null &!
            ;;
        tar|gz|tgz|xz|txz|bz2|tbz2|zip)
            return
            ;;
        *)
            ${EDITOR:-nvim} "${abs_items[@]}"
            ;;
    esac
}
