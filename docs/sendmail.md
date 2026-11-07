---
layout: doc
title: "Sending mail from cron and PHP: bongo sendmail"
nav_title: "bongo sendmail"
permalink: /docs/sendmail/
source: https://github.com/bongo-project/bongo/blob/main/docs/sendmail.md
---
{% raw %}
# Sending mail from cron and PHP: `bongo sendmail`

`bongo sendmail` reads a message on standard input and submits it to a Bongo
server the way `sendmail` does. Programs that expect `/usr/sbin/sendmail`
(cron, PHP's `mail()`, `logwatch`, `unattended-upgrades`) can use it unchanged.

It is an ordinary SMTP submission client. It logs in as one Bongo account on
port 465 (implicit TLS) or port 587 (STARTTLS) and sends the message. Every
control the server applies to a user applies here too: the send-as policy, rate
limits, DKIM signing and quota. There is no extra trust boundary and no secret
shared with the server beyond that account's password. The server may be on
another host.

## Install

```sh
sudo ln -s /usr/local/bin/bongo /usr/sbin/sendmail
```

When the binary is invoked by the exact name `sendmail` (for example
`/usr/sbin/sendmail`; `bongo-sendmail` does not count), it behaves as
`bongo sendmail`. `bongo sendmail ...` works too.

## Configuration file

The default is `/etc/bongo/sendmail.conf`; `--config path` overrides it. There
is deliberately no password flag or environment variable, because both are
visible to other users in the process list.

```hcl
host     = "mail.example.com"
port     = 465                    # 465 implicit TLS (default), 587 STARTTLS
# tls    = "implicit"             # or "starttls"; defaults from the port
username = "cron@example.com"     # the full account address
password = "an app password"     # or the account password, if the account allows it
# insecure_skip_verify = true     # self-signed dev certificate, loopback only
```

The format is HCL, the same as `bongo.hcl`, so there is one syntax to learn and
the project's existing parser is reused. A bare `key=value` file would have
needed its own quoting rules for passwords.

The file must belong to the user that runs the job and be unreadable by anyone
else:

```sh
sudo chown www-data /etc/bongo/sendmail.conf      # the user running PHP-FPM or cron
sudo chmod 600 /etc/bongo/sendmail.conf
```

If the file is readable by its group or by others, the command refuses to read
it and exits 78. Each user who needs different credentials can point
`--config` at their own file.

The server's certificate is always verified, with TLS 1.2 or later.
`insecure_skip_verify` exists for the self-signed certificate of dev mode (`bongo serve --dev`),
and is refused unless `host` is a loopback address (`127.0.0.1`, `::1` or the
name `localhost`). With `tls = "starttls"` the command refuses to continue when
the server does not offer STARTTLS; it never sends the password unencrypted.

## Command line

| Flag | Meaning |
|------|---------|
| `-t` | Take recipients from the `To`, `Cc` and `Bcc` headers, in addition to any on the command line |
| `-f address` | Envelope sender |
| `-F name` | Display name for a generated `From` header |
| `-i`, `-oi` | A line holding only a dot does not end the input |
| `--config path` | Configuration file |
| `-odi`, `-odb`, `-oem`, `-v`, `-bm`, `-B<type>` | Accepted and ignored |

`-bs` (SMTP on stdin) and every other flag exit 64. Without `-i` the input
ends at end-of-file or a line holding a single dot.

The command converts LF to CRLF, removes every `Bcc` header (the Bcc recipients
are still delivered to), and adds `Date`, `Message-ID` and, when absent, `From`.
Dot-stuffing is done by the SMTP layer.

### Addresses without a domain

The account is a full address, and the server only lets it send as addresses it
owns. Cron writes `From: root (Cron Daemon)` and some versions pass `-f root`.
So that these work:

- an envelope sender from `-f` without an `@` is replaced by the account address;
- a `From` header whose address has no domain is rewritten to the account
  address, keeping the display name (`"Cron Daemon" <cron@example.com>`);
- a qualified address the account may not send as is submitted unchanged and
  refused by the server (exit 77).

A recipient without a domain is refused with exit 64: the command cannot know
which domain to use.

## Cron

Set `MAILTO` to a full address. `MAILTO=root` fails with exit 64.

```cron
MAILTO=admin@example.com
0 3 * * * /usr/local/bin/backup.sh
```

Cron runs `sendmail` as the user the job runs as, so the configuration file
must be readable by that user (and nobody else). Debian and Ubuntu cron call
`sendmail -FCronDaemon -i -B8BITMIME -oem -oi`; cronie calls `sendmail -f root`.
Both are supported.

## PHP

```ini
sendmail_path = "/usr/sbin/sendmail -t -i"
```

PHP-FPM runs as its pool user, for example `www-data`; give that user the
configuration file. Set the `From` header in `mail()` to the account address or
to an address the account is allowed to send as.

## Exit codes

| Code | Name | Meaning |
|------|------|---------|
| 0 | | Accepted by the server |
| 64 | `EX_USAGE` | Unsupported flag, no recipients, recipient without a domain, control character in `-f` or `-F` |
| 65 | `EX_DATAERR` | Malformed headers; message or header too large; server rejected the header (`550 5.6.x`, `552 5.3.4`) |
| 67 | `EX_NOUSER` | A recipient was refused (any 5xx at `RCPT`). Nothing is sent to the others |
| 69 | `EX_UNAVAILABLE` | Cannot connect, TLS failure, STARTTLS missing, `421`, no `AUTH`, other permanent failures, mailbox quota (`552 5.2.2`) at `DATA` |
| 75 | `EX_TEMPFAIL` | Any other 4xx reply, or the connection dropped mid-session: try again later |
| 77 | `EX_NOPERM` | Authentication refused (`535`); the sender or `From` is not an address the account may send as (`553`/`550 5.7.x` at `MAIL` or `DATA`) |
| 78 | `EX_CONFIG` | Configuration missing, unreadable, invalid, or accessible by group or others |

The same reply means different things in different steps, so the code depends on
the step: `550 5.1.1 Mailbox unavailable` at `RCPT` (an unknown address on a
domain the server hosts, or a typo) is 67, while `550 5.7.1 From address not
owned by authenticated user` at `DATA` is 77. On any failure the
server's reply is printed on standard error. The password is never printed or
logged, and `-v` does nothing.

If one recipient is refused, the transaction is abandoned and the message goes
to nobody; the exit code is 67. The caller can then retry with the valid
recipients.
{% endraw %}
