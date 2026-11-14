---
layout: doc
title: "Config reload"
nav_title: "Config reload"
permalink: /docs/config-reload/
source: https://github.com/bongo-project/bongo/blob/main/docs/config-reload.md
---
{% raw %}
# Config reload

Bongo reloads its configuration file on SIGHUP. Some settings take effect
immediately; the rest take effect at the next restart. Mail, IMAP and web
sessions stay connected during a reload.

## Sending the signal

Edit the configuration file, then send SIGHUP to the `bongo` process:

```bash
docker compose kill -s HUP bongo     # Docker: the entrypoint runs bongo directly
systemctl reload bongo               # systemd: the unit's ExecReload sends SIGHUP
kill -HUP <pid>                      # any other process manager
```

SIGHUP never stops the server. A foreground `bongo serve` whose terminal
closes, and a process started under `nohup`, reload rather than exit. SIGINT
and SIGTERM stop the server.

A server started without a configuration file (for example `bongo serve --dev`
with no `--config`) logs `config reload: no config file in use, nothing to
reload`.

## Settings that reload

| Key | Effect |
|-----|--------|
| `telemetry.log.level` | Applies to the next log line. |
| `telemetry.log.components` | Per-component levels; apply to the next log line. Removing an entry returns that component to `telemetry.log.level`. |
| `antispam.builtin.threshold`, `antispam.builtin.high_threshold` | Applied together, from the next message scored. |
| `smtp.trusted_networks` | Applies from the next message, including on connections already open. |
| `antivirus.clamav.on_failure` | Applies from the next message scanned. |

A widened `smtp.trusted_networks` is logged at WARN with the old and new
lists. A narrowed one is logged at INFO.

## Settings that need a restart

Every other setting needs a restart. Each changed one is logged at WARN as
`config reload: key needs restart`, with the key name and whether it is a
secret. Values are never logged. The warning repeats on every reload until the
server restarts.

A few keys are not read by the server. A change to one of them is listed under
`no_effect` in the summary line.

## Flags and environment

Command-line flags and `BONGO_*` environment variables take precedence over
the file. The overridable settings are `BONGO_ROLE`, `BONGO_BIND`,
`BONGO_JOIN` and `BONGO_WEB_SESSION_SECRET` (and `BONGO_CONFIG`, which picks
the file), plus the matching flags and `--log-level`. A key set by a flag or
the environment keeps that value; the file value is ignored and logged as
`config reload: key shadowed by flag or env, file value ignored`.

The environment is read once, at start. A changed `/etc/bongo/bongo.env`
(systemd) or Compose `.env` / `environment:` needs a restart. With Compose,
`docker compose up -d` recreates the container with the new environment;
`docker compose restart` keeps the old one.

## Validation

The file is parsed and validated in full before anything is applied, with the
same checks as at startup. If parsing or validation fails, the reload logs
`config reload failed` and every running value stays as it was. Parse errors
are logged as a position and a summary only, so a value from the file never
reaches the log.

## Log output

Every reload ends with one INFO line, `config reload complete`, with these
attributes:

| Attribute | Contents |
|-----------|----------|
| `file` | The file that was read |
| `applied` | Keys applied |
| `needs_restart` | Changed keys that need a restart |
| `no_effect` | Changed keys the server does not read |
| `shadowed` | Keys set by a flag or the environment |
| `file_mtime`, `file_size` | Modification time (UTC) and size of the file as read |

To check a reload:

```bash
docker compose logs --tail 30 bongo | grep 'config reload'
```

## Docker single-file bind mounts

The shipped Compose file mounts the configuration as a single file. An editor
that saves by writing a new file and renaming it creates a new inode, and the
container keeps seeing the old file until it restarts. Edit the file in
place, or check what the container sees before sending the signal:

```bash
docker compose exec bongo cat /etc/bongo/bongo.hcl
```

`file_mtime` and `file_size` in the summary line show which version was read.

## Clusters

Configuration is per node. SIGHUP reloads only the node that receives it. In a
cluster, edit the file and send the signal on every node. Cluster settings
(`cluster.*`), ports, TLS files and `server.name` all need a restart, so a
reload cannot change how nodes connect to each other.

## Design

The classification of every key and the reasoning behind the reload flow are
in [docs/design/config-reload.md](https://github.com/bongo-project/bongo/blob/main/docs/design/config-reload.md).
{% endraw %}
