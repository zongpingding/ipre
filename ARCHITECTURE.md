# ipre Architecture and Execution Flow

The core flow is simple: **`ipre` starts fzf; fzf invokes the backend in response
to user actions; the backend reads and updates state, performs file operations,
and calls `pre` to generate previews.**

## Execution Flow

The following Mermaid source describes the main components and their interactions.

```mermaid
flowchart TD
    START(["User runs ipre"]) --> INIT

    subgraph FRONT["Entry Point and Interaction: ipre"]
        INIT["Parse startup arguments<br/>Initialize this session's state directory<br/>Configure keybindings, previews, and exit cleanup"]
        UI["Main fzf interface<br/>List display, filename search, and multi-selection"]
        EXIT["ipre handles the exit result<br/>Files: invoke the backend opener<br/>Directory or Alt+q: write cwd-file when configured"]
        CLEAN["Remove this session's runtime state"]
    end

    subgraph BACK["Operation Layer: ipre_backend"]
        DISPATCH["Receive an ipre_action_* invocation<br/>Decode path arguments and read session state"]
        LIST["Generate the listing<br/>Apply depth, type, and hidden-file rules<br/>Build display fields and sort when applicable"]
        ACTION["Navigation and file operations<br/>History, view mode, copy, cut, and paste<br/>Rename, delete, bookmarks, and more"]
        PREVIEW["Preview control<br/>Track the current file, page, and page navigation"]
        OPEN["Shared opening logic<br/>Classify each file and choose its application"]
        UPDATE["Return list records, status text,<br/>or fzf action instructions"]
    end

    subgraph MODULES["Supporting Scripts"]
        PATHS["ipre_paths<br/>Path encoding and decoding<br/>Display escaping, record generation, and state access"]
        PALETTE["ipre_palette<br/>Command menus and prompts<br/>Open with, archive operations, restore, checksums, and more"]
        PRE["pre<br/>File type detection and content previews<br/>Exposes get_file_type for external callers"]
    end

    subgraph EXTERNAL["External Tools and Storage"]
        FD["fd<br/>Emit original paths separated by NUL"]
        STATE[("Session-local state<br/>Directory, history, filters, clipboard<br/>Selection, focus, view mode, and page")]
        DATA[("Data shared across sessions<br/>Bookmarks and trash")]
        CACHE[("Preview cache")]
        RENDER["Preview tools<br/>bat, eza, chafa<br/>pdftoppm, ddjvu, and others"]
        APP["External applications<br/>Text editor, image viewer<br/>Document viewer, media player, and others"]
    end

    INIT --> STATE
    INIT -->|"Initial listing request"| DISPATCH
    DISPATCH --> LIST
    LIST -->|"Run the scan"| FD
    FD -->|"Original path stream"| LIST
    LIST -->|"Encoded paths and display fields"| UI

    UI -->|"Query input: filter internally"| UI
    UI -->|"Keybindings, focus changes, and preview requests"| DISPATCH
    DISPATCH <-->|"Read and update"| STATE

    DISPATCH --> ACTION
    ACTION <-->|"Bookmarks, deletion, and related operations"| DATA
    ACTION --> UPDATE

    DISPATCH -->|"Command palette entry point"| PALETTE
    PALETTE <-->|"Restore, empty trash, and related operations"| DATA
    PALETTE -->|"Open with"| OPEN
    PALETTE --> UPDATE

    DISPATCH --> PREVIEW
    PREVIEW -->|"Original path and page number"| PRE
    PRE <-->|"Look up or generate thumbnails"| CACHE
    PRE --> RENDER
    RENDER -->|"Preview content"| UI

    DISPATCH -->|"Open files while keeping the interface active"| OPEN
    OPEN -->|"Call get_file_type"| PRE
    PRE -->|"Return file type"| OPEN
    OPEN --> APP
    OPEN --> UPDATE

    UPDATE -->|"Refresh the list, status, focus, or preview"| UI

    UI -->|"Default Enter, Ctrl+q, or Alt+q"| EXIT
    EXIT --> CLEAN
    CLEAN --> DONE(["Return to the shell<br/>A configured wrapper can change directory using cwd-file"])

    PATHS -.->|"Shared functions"| INIT
    PATHS -.->|"Shared functions"| DISPATCH
    PATHS -.->|"Build path records"| LIST
```

Solid arrows represent calls, data flow, or execution flow. Dotted arrows
represent shared-function dependencies.

## Script Responsibilities

| Script         | Responsibility                                                                                                                          |
|----------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| `ipre`         | Program entry point. Parses arguments, initializes session state, configures fzf keybindings, and handles exit and cleanup.             |
| `ipre_backend` | Core operation layer. Generates listings and handles navigation, file operations, preview control, and shared opening logic.            |
| `ipre_palette` | Command palette module loaded by the backend. Provides menus, prompts, and their associated operations.                                 |
| `ipre_paths`   | Shared library loaded by the entry point and backend. Implements the path protocol, display escaping, and part of the state management. |
| `pre`          | Standalone preview program. Also provides file type detection to the backend through `pre get_file_type`.                               |

## Four Key Operating Principles

### 1. fzf Drives Interaction; the Backend Runs on Demand

The backend is not a persistent service. fzf keybindings, preview requests, and
interface events launch the corresponding backend invocations.

These invocations use exported environment variables to locate **the same
session's state files**, preserving the current directory, clipboard, history,
and other state between calls.

### 2. Search and Directory Scanning Are Separate Steps

- **fd** scans the filesystem and produces candidate paths.
- **fzf** performs filename searches over the available candidates.
- Navigation and changes to depth or filtering rules trigger listing regeneration
  through the configured bindings.
- `depth=0` streams listing results without waiting for a global sort.

### 3. Operation Paths Are Separate from Display Content

The current listing record formats are:

```text
Compact:  encoded_absolute_path<TAB>display_name
Detailed: encoded_absolute_path<TAB>display_name<TAB>attributes<TAB>link_suffix
```

In detailed mode, fzf rearranges the visible fields:

```text
attributes → name → link suffix
```

**File operations always use the encoded path in the first field.** Icons,
column widths, `->` text, and display order do not change the actual operation
target.

### 4. Previewing and Opening Share File Type Detection

`pre` detects file types, invokes preview tools, and manages the thumbnail cache.
The backend manages page numbers and preview refreshes.

When opening files, the backend also calls `pre get_file_type`, then selects the
appropriate application. This function currently **checks known extensions first
and falls back to MIME detection for other cases**.
