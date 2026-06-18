# Inline (file) preview in zshell

# NOTE: maybe we can replace chafa by imgcat, which is faster.
function ipre() {
    local cmd cmd_str \
          FZF_STATE_FILE FZF_CWD_FILE FZF_HIDDEN_FILE \
          FZF_ACTION_CMD FZF_TARGETS_FILE FZF_CLIP_FILE
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

    # Parse arguments
    local start_dir="$PWD"
    local keep_open=0
    local -a extra_args target_dirs
    for arg in "$@"; do
        if [[ "$arg" == "--keep-open" || "$arg" == "--stay" || "$arg" == "--no-leave" ]]; then
            keep_open=1
        elif [[ -d "$arg" ]]; then
            target_dirs+=("$(realpath "$arg")")
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
    FZF_TARGETS_FILE="$HOME/.cache/pre_thumbs/fzf_targets"
    FZF_CLIP_FILE="$HOME/.cache/pre_thumbs/fzf_clip"
    FZF_ACTION_CMD="$HOME/.cache/pre_thumbs/fzf_action.sh"

    if [[ ${#target_dirs[@]} -eq 1 ]]; then
        start_dir="${target_dirs[1]}"
        printf "" > "$FZF_TARGETS_FILE"
    elif [[ ${#target_dirs[@]} -gt 1 ]]; then
        start_dir="$PWD"
        printf "%q " "${target_dirs[@]}" > "$FZF_TARGETS_FILE"
    else
        printf "" > "$FZF_TARGETS_FILE"
    fi

    echo "all" > "$FZF_STATE_FILE"
    echo "$start_dir" > "$FZF_CWD_FILE"
    echo "true" > "$FZF_HIDDEN_FILE" # default: show hidden files
    printf "" > "$FZF_CLIP_FILE"     # reset clipboard on startup

    # =========================================================
    # Generate external action router script.
    # =========================================================
    cat > "$FZF_ACTION_CMD" << EOF
#!/usr/bin/env bash
ACTION="\$1"
ITEM="\$2"

# Semantic UI Constants & Print Functions
C_RST='\033[0m'
C_RED='\033[1;31m'
C_GRN='\033[1;32m'
C_YLW='\033[1;33m'
C_CYN='\033[1;36m'
C_MAG='\033[1;35m'

print_title()  { printf "%b=== %s ===%b\n" "\$C_CYN" "\$1" "\$C_RST"; }
print_warn()   { printf "%b=== %s ===%b\n\n" "\$C_RED" "\$1" "\$C_RST"; }
print_label()  { printf "%b%s%b" "\$C_GRN" "\$1" "\$C_RST"; }
print_hl()     { printf "%b%s%b" "\$C_YLW" "\$1" "\$C_RST"; }
print_clip()   { printf "[%b%s: %d%b] " "\$C_MAG" "\$1" "\$2" "\$C_RST"; }

# Action Handlers
case "\$ACTION" in
    run)
        cd "\$(cat '$FZF_CWD_FILE')" || exit 1
        run_cmd="$cmd_str"
        targets="\$(cat '$FZF_TARGETS_FILE')"

        if [ "\$(cat '$FZF_HIDDEN_FILE')" = "true" ]; then
            run_cmd="\$run_cmd --hidden"
        fi
        if grep -qxF "directory" '$FZF_STATE_FILE'; then
            eval "\$run_cmd --type d \$targets"
        elif grep -qxF "all" '$FZF_STATE_FILE'; then
            eval "\$run_cmd \$targets"
        else
            eval "\$run_cmd --type f \$targets"
        fi
        ;;

    header)
        state="\$(cat '$FZF_STATE_FILE')"
        targets="\$(cat '$FZF_TARGETS_FILE')"

        if [ -n "\$targets" ]; then
            cwd="[Multiple Directories]"
        else
            cwd="\$(sed 's|^$HOME|~|' '$FZF_CWD_FILE')"
        fi

        clip_str=""
        if [ -s '$FZF_CLIP_FILE' ]; then
            op="\$(head -n 1 '$FZF_CLIP_FILE')"
            count=\$(( \$(wc -l < '$FZF_CLIP_FILE') - 1 ))
            if [ \$count -gt 0 ]; then
                clip_str="\$(print_clip "\$op" "\$count")"
            fi
        fi

        cd "\$(cat '$FZF_CWD_FILE')" || exit 0
        if [ -n "\$ITEM" ] && [ -f "\$ITEM" ]; then
            info="\$(printf '[%b%s%b]: %s' "\$C_YLW" "\$(du -sh "\$ITEM" 2>/dev/null | cut -f1)" "\$C_RST" "\$(file --brief "\$ITEM" 2>/dev/null)")"
        elif [ -n "\$ITEM" ]; then
            info="\$(file --brief "\$ITEM" 2>/dev/null || echo 'No file')"
        else
            info="Empty directory / No matches"
        fi
        printf '[%b%s: %s%b]\n%s%s' "\$C_CYN" "\$state" "\$cwd" "\$C_RST" "\$clip_str" "\$info"
        ;;

    switch)
        if grep -qxF 'file' '$FZF_STATE_FILE'; then
            echo 'directory' > '$FZF_STATE_FILE'
        elif grep -qxF 'directory' '$FZF_STATE_FILE'; then
            echo 'all' > '$FZF_STATE_FILE'
        else
            echo 'file' > '$FZF_STATE_FILE'
        fi
        "\$0" run
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
        printf "" > '$FZF_TARGETS_FILE'
        "\$0" run
        ;;

    left)
        cur="\$(cat '$FZF_CWD_FILE')"
        new="\$(realpath "\$cur/..")"
        echo "\$new" > '$FZF_CWD_FILE'
        echo 'all' > '$FZF_STATE_FILE'
        printf "" > '$FZF_TARGETS_FILE'
        "\$0" run
        ;;

    copy)
        shift
        cd "\$(cat '$FZF_CWD_FILE')" || exit 1
        if [ \$# -eq 0 ] || [ -z "\$1" ]; then exit 0; fi
        echo "COPY" > '$FZF_CLIP_FILE'
        for i in "\$@"; do realpath "\$i" >> '$FZF_CLIP_FILE'; done
        ;;

    cut)
        shift
        cd "\$(cat '$FZF_CWD_FILE')" || exit 1
        if [ \$# -eq 0 ] || [ -z "\$1" ]; then exit 0; fi
        echo "CUT" > '$FZF_CLIP_FILE'
        for i in "\$@"; do realpath "\$i" >> '$FZF_CLIP_FILE'; done
        ;;

    paste)
        if [ ! -s '$FZF_CLIP_FILE' ]; then exit 0; fi
        dest="\$(cat '$FZF_CWD_FILE')"
        op="\$(head -n 1 '$FZF_CLIP_FILE')"

        tail -n +2 '$FZF_CLIP_FILE' | while read -r src; do
            if [ -e "\$src" ]; then
                base="\$(basename "\$src")"
                target="\$dest/\$base"

                # Conflict Detection and Smart Renaming
                if [ -e "\$target" ]; then
                    if [ "\$op" = "CUT" ] && [ "\$src" = "\$target" ]; then
                        continue
                    fi

                    # handle files without ext | hidden files
                    name="\${base%.*}"
                    ext="\${base##*.}"
                    if [ "\$name" = "\$base" ] || [ -z "\$name" ]; then
                        name="\$base"
                        ext=""
                    else
                        ext=".\$ext"
                    fi

                    # find the minimal index
                    counter=1
                    while [ -e "\$dest/\${name}_copy\${counter}\${ext}" ]; do
                        counter=\$((counter + 1))
                    done
                    target="\$dest/\${name}_copy\${counter}\${ext}"
                fi

                if [ "\$op" = "COPY" ]; then
                    cp -r "\$src" "\$target"
                elif [ "\$op" = "CUT" ]; then
                    mv "\$src" "\$target"
                fi
            fi
        done

        if [ "\$op" = "CUT" ]; then
            printf "" > '$FZF_CLIP_FILE'
        fi
        ;;

    delete)
        shift
        cd "\$(cat '$FZF_CWD_FILE')" || exit 1
        if [ \$# -eq 0 ] || [ -z "\$1" ]; then exit 0; fi
        clear
        print_warn "WARNING: DELETE CONFIRMATION"
        printf 'Current Dir : %s\n' "\$(print_label "\$PWD")"
        printf 'Are you sure you want to permanently delete the following %d item(s)?\n' "\$#"
        for i in "\$@"; do
            printf '  %s\n' "\$(print_hl "\$i")"
        done
        printf '\nType "y" to confirm [y/N]: '
        read -re ans </dev/tty
        if [ "\$ans" = "y" ] || [ "\$ans" = "Y" ]; then
            rm -rf "\$@"
        fi
        ;;

    new)
        cd "\$(cat '$FZF_CWD_FILE')" || exit 1
        clear
        print_title "Create New"
        printf 'Current Dir : %s\n' "\$(print_label "\$PWD")"
        printf 'Syntax Hint : End with %s to create a directory.\n' "\$(print_hl "/")"
        printf 'Multiple    : Separate with commas (e.g., file1, dir2/, file3)\n\n'

        read -re -p "Enter name(s): " names </dev/tty
        if [ -n "\$names" ]; then
            echo "\$names" | awk -F',' '{for(i=1;i<=NF;i++) {gsub(/^[ \t]+|[ \t]+$/, "", \$i); if(length(\$i)>0) print \$i}}' | while IFS= read -r name; do
                case "\$name" in
                    */) mkdir -p "\$name" ;;
                    *)  mkdir -p "\$(dirname "\$name")"; touch "\$name" ;;
                esac
            done
        fi
        ;;

    open)
        shift
        cd "\$(cat '$FZF_CWD_FILE')" || exit 1
        if [ \$# -eq 0 ] || [ -z "\$1" ]; then exit 0; fi
        if [ \$# -eq 1 ] && [ -d "\$1" ]; then exit 0; fi

        first_file="\$1"
        ext="\$(echo "\${first_file##*.}" | tr '[:upper:]' '[:lower:]')"
        case "\$ext" in
            png|jpg|jpeg|gif|webp|bmp|tiff)
                nohup imv "\$@" >/dev/null 2>&1 &
                ;;
            pdf|djvu|epub|mobi)
                nohup zathura "\$@" >/dev/null 2>&1 &
                ;;
            tar|gz|tgz|xz|txz|bz2|tbz2|zip)
                ;;
            *)
                \${EDITOR:-nvim} "\$@" </dev/tty >/dev/tty
                ;;
        esac
        ;;
esac
EOF
    chmod +x "$FZF_ACTION_CMD"

    # Keybindings setup
    local -a fzf_binds=(
        'resize:refresh-preview'
        "focus,load:transform-header:\"$FZF_ACTION_CMD\" header {}"
        "\`:reload(\"$FZF_ACTION_CMD\" switch)"
        "alt-.:execute-silent(\"$FZF_ACTION_CMD\" hidden)+reload(\"$FZF_ACTION_CMD\" run)"
        'alt-p:toggle-preview'
        'alt-a:select-all'
        "alt-a:+execute-silent(cd \"\$(cat '$FZF_CWD_FILE')\" && realpath {+} | wl-copy)"
        "alt-y:execute-silent(cd \"\$(cat '$FZF_CWD_FILE')\" && realpath {} | wl-copy)"

        "alt-c:execute-silent(\"$FZF_ACTION_CMD\" copy {+})+reload(\"$FZF_ACTION_CMD\" run)"
        "alt-x:execute-silent(\"$FZF_ACTION_CMD\" cut {+})+reload(\"$FZF_ACTION_CMD\" run)"
        "alt-v:execute-silent(\"$FZF_ACTION_CMD\" paste)+reload(\"$FZF_ACTION_CMD\" run)"

        "alt-n:execute(\"$FZF_ACTION_CMD\" new)+reload(\"$FZF_ACTION_CMD\" run)"
        "alt-r:execute(\"$FZF_ACTION_CMD\" delete {+})+reload(\"$FZF_ACTION_CMD\" run)"
        "left:reload(\"$FZF_ACTION_CMD\" left)+clear-query"
        "right:reload(\"$FZF_ACTION_CMD\" right {})+clear-query"
    )
    if [[ $keep_open -eq 1 ]]; then
        fzf_binds+=("enter:execute(\"$FZF_ACTION_CMD\" open {+})")
    fi
    local -a fzf_args=(
        --multi
        --prompt "ipre > "
        --preview "cd \"\$(cat '$FZF_CWD_FILE')\" && printf '\033[2J\033[H'; pre {}"
        --height=50% --reverse
        --preview-window=right:60%
    )
    for b in "${fzf_binds[@]}"; do
        fzf_args+=(--bind "$b")
    done

    # Execute Fzf
    local -a selected_items
    selected_items=("${(@f)$(
        "$FZF_ACTION_CMD" run | fzf "${fzf_args[@]}"
    )}")

    # Post Actions (Only executes if NO --keep-open)
    if [[ ${#selected_items[@]} -eq 0 || -z "${selected_items[1]}" ]]; then
        return
    fi
    local final_cwd="$(cat "$FZF_CWD_FILE")"
    local -a abs_items
    for item in "${selected_items[@]}"; do
        if [[ "$item" == /* ]]; then
            abs_items+=("$item")
        else
            abs_items+=("$final_cwd/$item")
        fi
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
