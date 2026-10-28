# Path protocol (`paths-v1`)

## Paths and display text

`fd --print0` supplies the original paths, separated by NUL. A path is converted
to an absolute path without resolving the final symlink. Its bytes are percent
encoded: only `A-Z`, `a-z`, `0-9`, `/`, `.`, `_`, `~`, and `-` remain literal.
All other bytes become uppercase `%HH`. Thus a literal `%0A` is stored as
`%250A`, while a newline is stored as `%0A`. Non-UTF-8 filenames are preserved.

An fzf record has this format:

```text
encoded_absolute_path<TAB>display_text<LF>
encoded_absolute_path<TAB>display_text<TAB>metadata<TAB>link_suffix<LF>
```

The second format is used for detailed listings. The fourth field is empty for
non-symlinks; its preceding TAB must remain so fzf can reorder fields without
joining metadata and filename. Compact mode uses `--with-nth=2 --nth=1`;
detailed mode uses `--with-nth=3,2,4 --nth=2`. Both use `--delimiter=$'\t'` and
`--id-nth=1`. The display transform removes the path key, search matches only the
filename field in the transformed display, and identity comes from the original
encoded path. Detailed attributes have fixed widths and precede the filename;
the escaped `-> target` suffix follows it. Automatic horizontal scrolling is
disabled in detailed mode to preserve alignment. `reload-sync` preserves selections during a view
change; `track-current` preserves the cursor. The filename field contains
a relative name, optional icon/type marker, and a directory slash. Backslashes
and control characters are visibly escaped, so neither a raw TAB nor a raw LF
can enter that field. Display text is never decoded into an operation path.
Metadata is also escaped, is display-only, and does not participate in search.
Icons are chosen from file type/extension; eza/ls output is not parsed for paths.

Bound commands use `{1}` or `{+1}` and declare their input with `--encoded`.
fzf's accepted output retains the original records, and the frontend extracts
and decodes the first field. A malformed escape or `%00` is rejected. Decoding
is one pass and never executes the resulting text.

## Stored state

Navigation, clipboard, selection, focus, search roots and preview state belong
to the invocation's runtime directory. Each path value is encoded once:

| State                                | Format                                                   |
|--------------------------------------|----------------------------------------------------------|
| CWD, focus, last previewed file      | One encoded absolute path followed by LF                 |
| Selection, bookmarks, search roots   | One encoded absolute path per line                       |
| Back/forward directory history       | One encoded absolute path per line; newest entry last    |
| Clipboard                            | `COPY` or `CUT`, then one encoded absolute path per line |
| Cached fzf list                      | Original two- or four-field records                      |
| Position, page, depth, sort, view, notices | Ordinary non-path values                            |

The shared bookmark file is `bookmarks.paths-v1`. On its first creation, existing
literal line-based `bookmarks` are encoded without interpreting percent signs.
The legacy file is retained. Old records already broken by embedded newlines
cannot be reconstructed automatically.

Trash entries retain their existing lossless format: NUL-terminated `origin`
metadata and the original basename inside `payload/`.

The system clipboard and `--cwd-file` receive literal paths, not percent encoded
values. Multiple system clipboard paths remain newline separated for pasting
into other applications.

## Backend inputs

The default backend API takes literal arguments. Inputs are never classified by
looking for percent signs, icons, or arrows:

```zsh
ipre_backend ipre_action_copy 'literal%0A'
ipre_backend ipre_action_copy -- './--encoded'
ipre_backend ipre_action_copy --encoded '/tmp/literal%250A'
ipre_backend ipre_action_copy --records $'/tmp/literal%250A\tvisible label'
```

`--encoded` decodes the path arguments; `--records` extracts their first TAB
field before decoding. Directions in `ipre_action_smart_scroll` and line numbers
in `ipre_action_rg_preview` remain ordinary arguments. Internal function calls
use already decoded paths. `ipre_paths` provides the common codec, state and
record functions; decoded values are returned in `REPLY` to preserve trailing
newlines without command substitution.

## Name editors

Rename prompts, batch rename and the buffer editor show reversible text escapes:

| Text   | Literal value   |
|--------|-----------------|
| `\\`   | Backslash       |
| `\n`   | Newline         |
| `\t`   | TAB             |
| `\r`   | Carriage return |
| `\xHH` | A nonzero byte  |

Spaces, quotes, percent signs and arrows are ordinary text. Unknown escapes and
NUL are rejected. A name containing the two characters `\n` must be entered as
`\\n`.

Batch rename rows are `[id]<TAB>escaped_new_name`. Source paths are shown in
comments, while the actual source paths stay in memory and are identified by ID.
Changing a comment cannot change a source. Invalid, repeated or missing IDs abort
the edit before any move. New names are relative to each source's parent; the
existing staging and rollback rules are retained.

## Search and focus

Live grep reads rg's NUL-terminated filename followed by line/column/content
metadata. Its records are `encoded_path<TAB>line<TAB>column<TAB>display_text`;
the visible/searchable field is field 4. Colons inside filenames are ordinary
path bytes, and content is visibly escaped.

Focus compares encoded absolute identities in the first field, independently of
icons and visible directory slashes. Depth 0 lists stream without global sorting
or icons; focus is applied when the corresponding record becomes available.

Zoxide's external line-based output cannot recover directories containing LF.
For directory names supported by that interface, its picker also uses encoded
path records.
