---
layout: doc
title: "Importing Email into Bongo"
nav_title: "Importing mail"
permalink: /docs/importing/
source: https://github.com/bongo-project/bongo/blob/main/docs/importing.md
---
{% raw %}
# Importing Email into Bongo

The `bongo-import` tool migrates email from various sources into a running
bongo server via IMAP APPEND. The `directory` subcommand can also upload
contacts and calendar files through the web API.

## Build

```bash
make build
```

This builds both binaries into `bin/`; the import tool is `./bin/bongo-import`.

## Common Flags

All subcommands share these flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--dst-host` | `localhost` | Destination IMAP hostname |
| `--dst-port` | `1143` | Destination IMAP port |
| `--dst-tls` | `false` | Use TLS for destination |
| `--dst-user` | (required) | Destination username |
| `--dst-pass` | (required) | Destination password |
| `--state` | | Path to JSON state file for resume |
| `--dry-run` | `false` | List what would be imported without writing |

The `--dst-port` default of 1143 is the plain IMAP port that
`bongo serve --dev` listens on. Against a production server, use
`--dst-port 993 --dst-tls` for implicit TLS, or `--dst-port 143`.

The `--state` flag enables resumable imports. If the import is interrupted,
re-running with the same state file skips already-imported messages.

## Sources

### Thunderbird Local Folders

Auto-discovers Thunderbird's profile directory and imports all local folders,
preserving the folder hierarchy.

```bash
# Auto-discover (finds Thunderbird profile automatically)
./bin/bongo-import thunderbird --dst-user admin@localhost --dst-pass admin

# Specify a profile directory
./bin/bongo-import thunderbird --profile ~/Library/Thunderbird/Profiles/abc.default-release \
  --dst-user admin@localhost --dst-pass admin

# Specify the Local Folders directory directly
./bin/bongo-import thunderbird ~/Library/Thunderbird/Profiles/abc.default-release/Mail/Local\ Folders \
  --dst-user admin@localhost --dst-pass admin
```

Profile auto-discovery looks in:
- **macOS:** `~/Library/Thunderbird/Profiles/`
- **Linux:** `~/.thunderbird/`
- **Windows:** `%APPDATA%\Thunderbird\Profiles\`

Thunderbird folder mapping:
- `Inbox` becomes `INBOX`
- `Sent`, `Drafts`, `Trash`, `Junk` keep their names
- `Archives` becomes `Archive`
- Nested folders (`.sbd` directories) are preserved as `Parent/Child`
- `.msf` summary files, and `.dat` and `.html` files (such as
  `msgFilterRules.dat` and `filterlog.html`), are skipped

### IMAP (Server-to-Server)

Import from another IMAP server. All folders are migrated unless excluded.

```bash
./bin/bongo-import imap \
  --src-host mail.example.com \
  --src-user user@example.com --src-pass oldpassword \
  --dst-user admin@localhost --dst-pass admin
```

| Flag | Default | Description |
|------|---------|-------------|
| `--src-host` | (required) | Source IMAP hostname |
| `--src-port` | `993` | Source IMAP port |
| `--src-tls` | `true` | Use TLS for the source; pass `--src-tls=false` for a plain connection |
| `--src-user` | (required) | Source username |
| `--src-pass` | (required) | Source password |
| `--exclude` | | Source folder to skip; repeat for several (e.g. `--exclude "[Gmail]/All Mail"`) |
| `--folder-map` | | Rename a folder as `"Src=Dst"`; repeat for several (e.g. `--folder-map "Old Sent=Sent"`) |
| `--gmail` | `false` | Force Gmail mode |

Gmail mode is switched on automatically when `--src-host` contains
`gmail.com` or `googlemail.com`, or by `--gmail` for other hosts. In Gmail mode
folders are mapped from their IMAP special-use attributes rather than their
names, so localised folder names are handled:

- Sent, Drafts, Trash and Junk map to `Sent`, `Drafts`, `Trash` and `Junk`
- Starred (`\Flagged`) maps to `Starred`
- All Mail (`\All`) maps to `Archive`, is imported last, and messages already
  imported from another folder are skipped by Message-ID
- Important and any `\NoSelect` folder are skipped

Explicit `--folder-map` and `--exclude` values take precedence over the
automatic Gmail mapping.

### Mbox Files

Import one or more mbox files into a single folder.

```bash
# Import into INBOX (default)
./bin/bongo-import mbox ~/mail/inbox.mbox --dst-user admin@localhost --dst-pass admin

# Import into a specific folder
./bin/bongo-import mbox --folder "Archive/2024" ~/mail/archive.mbox \
  --dst-user admin@localhost --dst-pass admin

# Import multiple files
./bin/bongo-import mbox ~/mail/*.mbox --dst-user admin@localhost --dst-pass admin
```

### Maildir

Import from a Maildir directory. Maildir++ subfolder conventions are
supported (e.g., `.Sent`, `.Drafts`).

```bash
./bin/bongo-import maildir ~/Maildir --dst-user admin@localhost --dst-pass admin
```

### EML Files

Import individual `.eml` files.

```bash
./bin/bongo-import eml --folder INBOX ~/exports/*.eml \
  --dst-user admin@localhost --dst-pass admin
```

### Directory (Mail, Contacts and Calendar)

Recursively scan a directory and import everything recognised in it:

- `.mbox` and `.mbx` files are imported as mail
- `.eml` files are imported as mail, one folder per parent directory
- Maildir directories (any directory containing `cur/` or `new/`) are imported
  as mail
- `.vcf` files are uploaded as contacts through the web API
- `.ics` files are uploaded as calendar events through the web API

Mail goes through IMAP APPEND using the common `--dst-*` flags. Files directly
in the given directory go to `INBOX`; files in subdirectories go to a folder
named after the relative path (e.g. `Archive/2024`). Contacts and calendar
files are uploaded by logging in to the web UI with the same `--dst-user` and
`--dst-pass`. The tool prints a summary of what it found and asks for
confirmation before importing.

```bash
./bin/bongo-import directory ~/export \
  --dst-user admin@localhost --dst-pass admin
```

| Flag | Default | Description |
|------|---------|-------------|
| `--web-url` | `https://localhost:8080` | Web base URL for contact and calendar uploads |
| `--mail-only` | `false` | Import only mail |
| `--contacts-only` | `false` | Import only `.vcf` files |
| `--calendar-only` | `false` | Import only `.ics` files |
| `--yes` | `false` | Skip the confirmation prompt |

A dev server (`bongo serve --dev`) always serves the web UI over plain
HTTP, so pass `--web-url http://localhost:8080`. The tool does not verify the web
server's TLS certificate, and it logs in with the destination password over
that connection; run it only over a network path you trust.

## Resumable Imports

For large migrations, use the `--state` flag to track progress:

```bash
./bin/bongo-import thunderbird --state ~/.bongo-import-state.json \
  --dst-user admin@localhost --dst-pass admin
```

If interrupted, re-run the same command. Already-imported messages are skipped.

## Dry Run

Preview what would be imported without writing anything:

```bash
./bin/bongo-import thunderbird --dry-run --dst-user admin@localhost --dst-pass admin
```
{% endraw %}
