---
layout: doc
title: "Installing Bongo from the binary release"
nav_title: "Install"
permalink: /docs/install/
source: https://github.com/bongo-project/bongo/blob/main/docs/install.md
---
{% raw %}
# Installing Bongo from the binary release

This guide installs and runs a Bongo mail + calendar server from a release zip —
no Docker, no build toolchain. Everything (web assets, templates, translations)
is embedded in a single self-contained binary.

If you would rather run under Docker + Traefik, see
[`../deploy/README.md`](https://github.com/bongo-project/bongo/blob/main/deploy/README.md) instead.

---

## 1. What's in the zip

Download the zip for your architecture from the
[GitHub releases page](https://github.com/bongo-project/bongo/releases), or
build the same zips from a source checkout with `make dist` (they land in
`dist/`).

```
bongo_<version>_linux_<arch>/
  bongo                # the server binary
  bongo-import            # mail import tool (mbox/maildir/eml/IMAP/Thunderbird)
  bongo.example.hcl       # fully annotated example configuration
  bongo.service        # systemd unit template
  INSTALL.md              # this guide
  README.md               # what this release is and what is not finished yet
  LICENSE                 # licence text
  THIRD_PARTY_NOTICES.md  # licences of bundled third-party components
```

`<arch>` is `amd64` (Intel/AMD x86-64) or `arm64` (ARM 64-bit, e.g. Raspberry
Pi 4/5, AWS Graviton). Pick the zip matching your machine — check with
`uname -m` (`x86_64` -> amd64, `aarch64` -> arm64).

The binaries are statically linked and have **no runtime dependencies** — no
libc, no database server, nothing to install alongside them.

---

## 2. Prerequisites

**To try it locally** you need nothing but the binary.

**To run a real, internet-facing mail server** you also need, outside this
software:

- A host that allows **outbound TCP port 25** (many cloud/VPS providers block
  it — if yours does, use an SMTP relay; see step 7).
- A **static IP** with a matching **PTR (reverse DNS)** record pointing at your
  mail hostname (e.g. `mail.example.com`).
- Control of your domain's **DNS** to publish A / MX / SPF / DKIM / DMARC
  records (the admin UI generates the exact records for you).
- A **TLS certificate** for the mail hostname (e.g. from Let's Encrypt).
  Without one, IMAP and POP3 fall back to a self-signed certificate (fine for
  testing; real clients will not trust it), and SMTP offers no STARTTLS at all,
  so authenticated submission on port 587 is unavailable because AUTH is only
  offered over TLS.
- Ports open: `25`, `587` (SMTP), `465` (SMTP over implicit TLS; needs `smtp.tls`, otherwise it is not started), `143`, `993` (IMAP), optionally `110`, `995`
  (POP3), and `443` (web UI). Binding ports below 1024 needs root or a
  capability grant (see step 6).

---

## 3. Install the files

```bash
unzip bongo_<version>_linux_<arch>.zip
cd bongo_<version>_linux_<arch>

# Binaries onto PATH
sudo install -m 0755 bongo bongo-import /usr/local/bin/

# Config directory
sudo mkdir -p /etc/bongo
sudo cp bongo.example.hcl /etc/bongo/bongo.hcl

# Data + log directories
sudo mkdir -p /var/lib/bongo /var/log/bongo
```

The server discovers its config file in this order:
`--config` flag > `BONGO_CONFIG` env var > `./bongo.hcl` > `/etc/bongo/bongo.hcl`.
Putting it at `/etc/bongo/bongo.hcl` means you can just run `bongo serve`.

---

## 4. Quickest possible test (no config, no DNS)

To confirm the binary runs on your machine before doing any real setup:

```bash
bongo serve --dev
```

Dev mode uses ephemeral storage, runs the mail protocols on high ports, and
auto-creates a login of `admin@localhost` / `admin`. The mail protocols' TLS
ports use a self-signed certificate. The web UI is always served over
plain **http** in dev mode (no TLS, so no certificate warning) at
<http://localhost:8080> — do not use dev mode anywhere untrusted, since the
password crosses the network in clear. Stop it with Ctrl-C — nothing is
persisted.

---

## 5. Configure a real server

Edit `/etc/bongo/bongo.hcl`. Every option is documented inline in the example.
The minimum you must change for a real single-domain server:

1. **Hostname** — set `smtp.hostname` to your mail host, e.g.
   `hostname = "mail.example.com"`.
2. **TLS certificates** — point the cert/key at your certificate. IMAP (993) and
   POP3 (995) read theirs from the `cluster.tls` block; SMTP reads `smtp.tls`;
   the web UI reads `web.tls`. Use the same fullchain/key for all three:
   ```hcl
   cluster { tls { cert_file = "/etc/bongo/certs/fullchain.pem"
                   key_file  = "/etc/bongo/certs/privkey.pem" } }
   smtp    { tls { cert_file = "/etc/bongo/certs/fullchain.pem"
                   key_file  = "/etc/bongo/certs/privkey.pem" } }
   web     { tls { cert_file = "/etc/bongo/certs/fullchain.pem"
                   key_file  = "/etc/bongo/certs/privkey.pem" } }
   ```
   (Behind a TLS-terminating reverse proxy instead? Set `web.plain_http = true`
   and `web.behind_tls_proxy = true`, change `web.port` to `8080`, and list the
   proxy's address in `server.trusted_proxies`; without it `X-Forwarded-For`
   and `X-Forwarded-Proto` are ignored, so rate limits and lockout see the
   proxy's IP and HSTS is not sent.)
3. **Session secret** — generate one and keep it out of the file:
   ```bash
   openssl rand -base64 32
   ```
   Export it as `BONGO_WEB_SESSION_SECRET` (the systemd unit reads it from an
   environment file — see step 6). The same secret is needed to create the first
   admin (step 8).
4. **DNS** — publish A, `MX -> mail.example.com`, SPF (`v=spf1 mx ~all`) and
   DMARC (`p=none` to start) records, plus the PTR for the mail host. The admin
   UI's per-domain page generates the exact record set (and a BIND zone).

### DKIM (recommended)

Generate a signing key and enable the `smtp.dkim` block:

```bash
sudo mkdir -p /etc/bongo/secrets
sudo openssl genrsa -out /etc/bongo/secrets/dkim.key 2048
sudo openssl rsa -in /etc/bongo/secrets/dkim.key -pubout -outform DER 2>/dev/null \
  | openssl base64 -A            # this is the p= value for the DNS TXT record
```

```hcl
smtp {
  dkim {
    selector         = "mail"
    domain           = "example.com"
    private_key_file = "/etc/bongo/secrets/dkim.key"
  }
}
```

Publish the public key as a TXT record at `mail._domainkey.example.com`
(`v=DKIM1; k=rsa; p=<base64 from above>`).

Alternatively, once the server is running, generate a key per domain in the web
UI under **Admin → Domains → Manage**. The page shows the DNS TXT record to
publish, and no key file or `smtp.dkim` block is needed for that domain.

---

## 6. Run as a service (systemd)

The included `bongo.service` runs the server as a dedicated user, restarts on
failure, and grants the capability to bind low ports without running as root.

```bash
# Dedicated system user
sudo useradd --system --home /var/lib/bongo --shell /usr/sbin/nologin bongo || true
sudo chown -R bongo:bongo /var/lib/bongo /var/log/bongo /etc/bongo

# Secret in an environment file (root-only)
echo "BONGO_WEB_SESSION_SECRET=$(openssl rand -base64 32)" | sudo tee /etc/bongo/bongo.env >/dev/null
sudo chmod 600 /etc/bongo/bongo.env

# Install and start the unit
sudo cp bongo.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bongo

# Watch it come up
journalctl -u bongo -f
```

---

## 7. External SMTP relay (smarthost)

If your host blocks outbound port 25, or you must send through a provider
(SendGrid, Mailgun, your ISP's smarthost), enable the relay block in
`bongo.hcl`. All outbound mail then goes through that server instead of
direct-to-MX:

```hcl
smtp {
  relay {
    enabled  = true
    host     = "smtp.provider.com:587"   # host:port of the smarthost
    username = "you@example.com"         # SMTP AUTH username (omit for none)
    password = "your-app-password"       # SMTP AUTH password
    # allow_insecure_auth = false        # only for a trusted link with no STARTTLS
  }
}
```

How it works: Bongo connects to the smarthost, performs opportunistic STARTTLS,
and sends `AUTH PLAIN` **only after TLS succeeds**. If the link cannot be
encrypted it refuses to send the credentials unless you explicitly set
`allow_insecure_auth = true` (use only on a trusted private network). Permanent
(5xx) recipient rejections are reported back; transient failures are retried
from the outbound queue.

When `enabled = false`, Bongo delivers directly to each recipient's MX. The
`mta_sts_enabled` / `dane_enabled` options (also in the relay block) harden that
direct-to-MX path and are ignored when a smarthost is in use.

---

## 8. Create the first admin user

Production does not auto-create a login. With the server running, create one by
calling its internal endpoint (authenticated with the session secret):

```bash
bongo user create \
  --email you@example.com \
  --password 'a-strong-password' \
  --admin \
  --http-addr http://127.0.0.1:8081 \
  --session-secret "$BONGO_WEB_SESSION_SECRET"
```

`--http-addr` must point at the running node's control listener
(`server.control_addr`, default `http://127.0.0.1:8081`, always plain HTTP and
loopback only). The `/internal/*` routes are not served on the public web
port. If you change `server.control_addr`, pass the new address here, because
the CLI does not read the server config.
`--session-secret` must match the node's
`web.session_secret`; it also falls back to the `BONGO_WEB_SESSION_SECRET`
environment variable. Then log in to the web UI.

You do not need to add your primary domain: on startup the server adds it as a
managed domain, taking `smtp.dkim.domain` or, if that is unset, the registered
domain of `smtp.hostname` (`example.com` for `mail.example.com`). Add any
further domains under **Admin → Domains**; they are managed at runtime, not in
the config file.

### Listing users, domains and aliases

Three read-only commands list what the server holds, without the web UI. They
use the same control listener and session secret as `user create`:

```bash
bongo user list   [--domain example.com] [--json]
bongo domain list [--json]
bongo alias list  [--domain example.com] [--json]
```

- `user list` prints email, display name, enabled or disabled, global admin and
  the domains the account administers.
- `domain list` prints each hosted domain with its status, `alias_of` (set for a
  domain alias), catch-all target, user and storage quota, usage and whether a
  DKIM key exists. The key itself is never shown.
- `alias list` prints **address** aliases (an alias address and the account it
  delivers to), not domain aliases. Domain aliases are in the `ALIAS OF` column
  of `domain list`.
- `--domain` keeps only addresses ending in `@example.com`; subdomains do not
  match. `--json` prints a JSON array with the same fields as the table.
- `--http-addr` and `--session-secret` work as for `user create`; `--http-addr`
  accepts `host:port` or `http://host:port`. If the server cannot be reached
  the command prints one line naming the control address and exits non-zero.

The data comes from the node's own Pebble store, never from passwords, TOTP
secrets, recovery codes, DKIM keys or session material. A follower may lag the
leader by a few log entries. Each list is sorted and capped at 100000 rows; if
it is cut, the command still prints what it has, warns on stderr and exits
non-zero (narrow it with `--domain`). An older node that lacks these routes
answers 404, which the command reports as such.

---

## 9. Importing existing mail

`bongo-import` ingests mail from mbox, maildir, `.eml`, IMAP and Thunderbird
profiles. See [`importing.md`](/docs/importing/).

Cron jobs and web applications on the same host can send mail through
`bongo sendmail`, a sendmail-compatible submission client. See
[`sendmail.md`](/docs/sendmail/).

---

## 10. Upgrading

Stop the service, replace the two binaries, start it again — data in
`/var/lib/bongo` and your config are untouched:

```bash
sudo systemctl stop bongo
sudo install -m 0755 bongo bongo-import /usr/local/bin/
sudo systemctl start bongo
bongo version   # confirm the new version
```
{% endraw %}
