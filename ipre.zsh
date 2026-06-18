# Inline (file) preview in zshell

# NOTE: 
#  1. maybe we can replace chafa by imgcat, which is faster.
#  2. 'transform-prompt' does NOT evaluate danymiclly.
#  2. maybe we can use 'skim' - just like fzf but in Rust.
function ipre() {
    local cmd cmd_str FZF_STATE_FILE FZF_CWD_FILE FZF_HIDDEN_FILE FZF_ACTION_CMD
    if [[ -n "$IPRE_FD" ]]; then
        cmd=(${=IPRE_FD})
    else
        cmd=(
            fd --follow
            -E .git -E target -E .cargo -E build -E .npm -E node_modules
            -E .cache -E dist -E out -E lsp-bridge
            -E .java -E .gradle -E .nuget -E .steam -E .android
            -E .ipython -E .vscode -E .vscode-oss -E .oh-my-zsh
            -E .emacs-tmp -E .pub-cache -E .proxyman
            . # search all patterns
        )
    fi
    # Separate directory argument from fd command flags
    local start_dir="$PWD"
    local -a extra_args
    for arg in "$@"; do
        if [[ -d "$arg" ]]; then
            start_dir="$(realpath "$arg")"
        else
            extra_args+=("$arg")
        fi
    done
    if [[ ${#extra_args[@]} -gt 0 ]]; then
        cmd+=("${extra_args[@]}")
    fi
    cmd_str=$(printf '%q ' "${cmd[@]}")
    # Initialize State
    mkdir -p "$HOME/.cache/pre_thumbs"
    FZF_STATE_FILE="$HOME/.cache/pre_thumbs/fzf_state"
    FZF_CWD_FILE="$HOME/.cache/pre_thumbs/fzf_cwd"
    FZF_HIDDEN_FILE="$HOME/.cache/pre_thumbs/fzf_hidden"
    FZF_ACTION_CMD="$HOME/.cache/pre_thumbs/fzf_action.sh"
    echo "all" > "$FZF_STATE_FILE"
    echo "$start_dir" > "$FZF_CWD_FILE"
    echo "true" > "$FZF_HIDDEN_FILE" # default: show hidden files

    # =========================================================
    # Generate an external action router script.
    # This prevents ANY quoting/escaping syntax bugs in fzf.
    # =========================================================
    cat > "$FZF_ACTION_CMD" << EOF
#!/bin/sh
ACTION="\$1"
ITEM="\$2"

case "\$ACTION" in
    run)
        cd "\$(cat '$FZF_CWD_FILE')" || exit 1
        run_cmd="$cmd_str"
        if [ "\$(cat '$FZF_HIDDEN_FILE')" = "true" ]; then
            run_cmd="\$run_cmd --hidden"
        fi
        if grep -qxF "directory" '$FZF_STATE_FILE'; then
            eval "\$run_cmd --type d"
        elif grep -qxF "all" '$FZF_STATE_FILE'; then
            eval "\$run_cmd"
        else
            eval "\$run_cmd --type f"
        fi
        ;;
        
    header)
        state="\$(cat '$FZF_STATE_FILE')"
        cwd="\$(sed 's|^$HOME|~|' '$FZF_CWD_FILE')"
        cd "\$(cat '$FZF_CWD_FILE')" || exit 0
        
        # Safely quote "\$ITEM" to prevent syntax errors with spaces
        if [ -n "\$ITEM" ] && [ -f "\$ITEM" ]; then
            info="\$(printf '[\033[1;33m%s\033[0m]: %s' "\$(du -sh "\$ITEM" 2>/dev/null | cut -f1)" "\$(file --brief "\$ITEM" 2>/dev/null)")"
        elif [ -n "\$ITEM" ]; then
            info="\$(file --brief "\$ITEM" 2>/dev/null || echo 'No file')"
        else
            info="Empty directory / No matches"
        fi
        printf '[\033[1;36m%s: %s\033[0m]\n%s' "\$state" "\$cwd" "\$info"
        ;;
        
    switch)
        if grep -qxF 'file' '$FZF_STATE_FILE'; then
            echo 'directory' > '$FZF_STATE_FILE'
        elif grep -qxF 'directory' '$FZF_STATE_FILE'; then
            echo 'all' > '$FZF_STATE_FILE'
        else
            echo 'file' > '$FZF_STATE_FILE'
        fi
        "\$0" run # trigger list generation
        ;;
        
    hidden)
        if [ "\$(cat '$FZF_HIDDEN_FILE')" = "true" ]; then
            echo 'false' > '$FZF_HIDDEN_FILE'
        else
            echo 'true' > '$FZF_HIDDEN_FILE'
        fi
        ;;
        
    right)
        cur="\$(cat '$FZF_CWD_FILE')"
        cd "\$cur" || exit 1
        if [ -n "\$ITEM" ]; then
            if [ -d "\$ITEM" ]; then
                new="\$(realpath "\$ITEM")"
            else
                new="\$(realpath "\$(dirname "\$ITEM")")"
            fi
            echo "\$new" > '$FZF_CWD_FILE'
        fi
        echo 'all' > '$FZF_STATE_FILE'
        "\$0" run
        ;;
        
    left)
        cur="\$(cat '$FZF_CWD_FILE')"
        new="\$(realpath "\$cur/..")"
        echo "\$new" > '$FZF_CWD_FILE'
        echo 'all' > '$FZF_STATE_FILE'
        "\$0" run
        ;;
esac
EOF
    chmod +x "$FZF_ACTION_CMD"

    # Execute Fzf
    local -a selected_items
    selected_items=("${(@f)$(
        "$FZF_ACTION_CMD" run | fzf \
        --multi \
        --prompt "ipre > " \
        --preview "cd \"\$(cat '$FZF_CWD_FILE')\" && printf '\033[2J\033[H'; pre {}" \
        --height=50% --reverse \
        --preview-window=right:60% \
        --bind 'resize:refresh-preview' \
        --bind "focus,load:transform-header:\"$FZF_ACTION_CMD\" header {}" \
        --bind "\`:reload(\"$FZF_ACTION_CMD\" switch)" \
        --bind "alt-.:execute-silent(\"$FZF_ACTION_CMD\" hidden)+reload(\"$FZF_ACTION_CMD\" run)" \
        --bind 'alt-p:toggle-preview' \
        --bind 'alt-a:select-all' \
        --bind "alt-a:+execute-silent(cd \"\$(cat '$FZF_CWD_FILE')\" && realpath {+} | wl-copy)" \
        --bind "alt-y:execute-silent(cd \"\$(cat '$FZF_CWD_FILE')\" && realpath {} | wl-copy)" \
        --bind "alt-r:execute-silent(cd \"\$(cat '$FZF_CWD_FILE')\" && rm -rf {}) + reload(\"$FZF_ACTION_CMD\" run)" \
        --bind "left:reload(\"$FZF_ACTION_CMD\" left)+clear-query" \
        --bind "right:reload(\"$FZF_ACTION_CMD\" right {})+clear-query"
    )}")

    # Post Actions
    if [[ ${#selected_items[@]} -eq 0 || -z "${selected_items[1]}" ]]; then
        return
    fi
    local final_cwd="$(cat "$FZF_CWD_FILE")"
    local -a abs_items
    for item in "${selected_items[@]}"; do
        abs_items+=("$final_cwd/$item")
    done
    local first_file="${abs_items[1]}"
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
