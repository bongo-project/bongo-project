---
layout: doc
title: "Bongo: Full Walkthrough"
nav_title: "Walkthrough"
permalink: /docs/walkthrough/
source: https://github.com/bongo-project/bongo/blob/main/docs/walkthrough.md
---
{% raw %}
# Bongo: Full Walkthrough

A step-by-step guide to building, running and exploring Bongo, a mail and
calendar server shipped as a single Go binary with an HTMX web UI. The server
binary is `bongo`.

---

## Prerequisites

- **Go** at the version named in `go.mod` (currently 1.27): <https://go.dev/dl/>
- **templ CLI**, which compiles `.templ` templates into Go code:
  ```bash
  go install github.com/a-h/templ/cmd/templ@latest
  ```
- **Git**, to clone the repository
- A current web browser (Chrome, Firefox, Safari or Edge)

Optional, for testing with a real mail client:

- **Thunderbird**: <https://www.thunderbird.net>
- **swaks**, a command-line SMTP test tool: `brew install swaks` (macOS) or
  `apt install swaks` (Linux)

---

## Step 1: Clone and Build

```bash
git clone https://github.com/bongo-project/bongo.git
cd bongo
make build
```

`make build` runs `templ generate` and builds both binaries into `bin/`:

- `bongo`: the mail and calendar server
- `bongo-import`: the mail, contacts and calendar import tool

---

## Step 2: Start the Server in Dev Mode

The quickest route is one command:

```bash
make dev
```

It builds, starts a dev server, runs the validation suite, seeds test data and keeps the server running until you press Ctrl-C. Open
<http://localhost:8080> when it prints "Dev server ready".

To start the server on its own instead:

```bash
./bin/bongo serve --dev
```

Dev mode needs no configuration. It creates an ephemeral data directory
(deleted on shutdown), serves the web UI over plain HTTP, uses a self-signed
certificate for the mail protocols' TLS ports, creates a default admin user and listens on non-privileged ports, so it does not need
root. Logs are JSON lines on standard output.

### Dev Mode Ports

| Service         | Port  | Protocol                          |
|-----------------|-------|-----------------------------------|
| Web UI          | 8080  | Plain HTTP                        |
| Control         | 8081  | `/internal` endpoints, loopback only |
| SMTP inbound    | 2525  | Plain text                        |
| SMTP submission | 2587  | Authentication required           |
| SMTP submission (TLS) | 2465 | Implicit TLS, authentication required |
| IMAP            | 1143  | Plain / STARTTLS                  |
| IMAPS           | 1993  | Implicit TLS                      |
| POP3            | 1110  | Plain / STARTTLS                  |
| POP3S           | 1995  | Implicit TLS                      |

### Default Login

- **Email:** `admin@localhost`
- **Password:** `admin`

---

## Step 3: Open the Web UI

Open <http://localhost:8080> and log in with `admin@localhost` / `admin`.

After login the Inbox opens. It is empty until mail is sent or test data is
seeded.

---

## Step 4: Populate with Test Data

`make dev` seeds test data already. Against a dev server you started yourself,
run:

```bash
make seed
```

The seed creates three test users (`alice`, `bob` and `charlie`, all
`@localhost`), delivers a set of messages over SMTP (threads, HTML mail and
attachments), creates the folders `INBOX/Important`, `INBOX/Receipts` and
`Projects` with two subfolders, and adds contacts and calendar events. Seeding
is not idempotent: running it twice creates duplicate contacts and events.

---

## Step 5: Explore the Web UI

### Layout

- **Top bar:** the Bongo logo, mail search, a light/dark theme toggle and the
  account menu.
- **Sidebar:** three groups. **Mail** holds INBOX (with its subfolders), Sent,
  Drafts, Trash, Junk and Archive, plus the Unread, Starred and All Mail
  views. **Folders** holds your own folders. **Workspace** links to Calendar,
  Contacts, Filter Rules, Settings and, for administrators, Admin.
- On a narrow screen the sidebar collapses into a menu.

### Mail

- **Message list:** the toolbar above the list switches between three
  layouts: **List** (a message opens on its own page), **Two-pane** (the
  reading pane below the list) and **Three-pane** (the reading pane beside the
  list). In the pane layouts a click on a message opens it in the reading
  pane. The toolbar also has Refresh, Scan for spam and Compose.
- **Selecting messages:** tick the checkboxes to act on several messages at
  once. Messages can be dragged onto a folder in the sidebar to move them.
- **Right-click** a message row for a menu with open, reply, reply all,
  forward, mark read or unread, star, spam or not spam, create filter and
  delete.
- **Reading a message:** the message toolbar has Reply, Reply all, Forward,
  Archive, Move to, Delete and tags. **More** holds Export, View Original
  (the raw source with all headers) and Print. Remote images are blocked until
  you choose to load them.
- **Compose:** the Compose button in the sidebar, or `c`. The composer has
  recipient chips, Cc and Bcc, attachments, a choice of rich text or plain
  text, a From address when you have send-as addresses, and Save draft.
- **Search:** the search field in the top bar. `/` or Ctrl-K (Cmd-K on a Mac)
  moves focus to it.

### Keyboard shortcuts

Press `?` for the full list. Shortcuts are ignored while typing in a field.

| Key | Action |
|-----|--------|
| `j` / `k` | Next / previous message. In the pane layouts the message opens after a short pause. |
| `Enter` | Open the highlighted message |
| `r` | Reply |
| `s` | Star or unstar |
| `d` | Move to Trash (does nothing in Trash) |
| `c` | Compose |
| `/`, Ctrl-K | Focus search |
| `?` | Show the shortcut list |

### Calendar

- **Views:** Month, Week, Day and Agenda, switched with the buttons at the
  top. The arrows and **Today** move through dates.
- **New Event** creates an event; clicking a day or a time slot also creates
  one at that point.
- The calendar sidebar has a mini month, your calendars (tick to show or
  hide), event search, and import and export of `.ics` files.

### Contacts

- The contact list is on the left; a click shows the contact on the right,
  where it can be edited and saved.
- **New Contact** adds one. **Import vCard** and **Export vCard** move
  contacts in and out as `.vcf` files (macOS Contacts, Google Contacts and
  others).

### Settings

**Settings** in the sidebar opens a page with five tabs:

- **Appearance:** theme (light, dark or follow the OS), default mail layout
  and list density.
- **Display:** messages per page and infinite scroll.
- **Composition:** default reply (sender or all) and signature.
- **Localization:** language (English, German, Spanish or French) and time
  zone.
- **Forwarding:** forward incoming mail to verified external addresses, with
  an option to keep a local copy.

The settings sidebar also links to:

- **Filter Rules:** rules that sort incoming mail, for example move
  newsletters to a folder, star messages from a sender or forward matches.
- **Tags:** create, colour and order tags.
- **Security:** change password, set up two-factor authentication with
  recovery codes, and create app passwords for mail and calendar clients.
  Add a device shows an app password beside the server settings, or builds an
  Apple profile or QR code.

Send-as addresses are managed at `/settings/addresses`.

---

## Step 6: Explore the Admin Panel

Administrators see **Admin** in the Workspace group of the sidebar. It opens
<http://localhost:8080/admin>.

### Dashboard

Users, storage, uptime and node count, the version, Raft state and cluster
size, and a policy switch that requires two-factor authentication for all
users.

### Users

List users, create them, reset passwords and set quotas.

### Domains

The domains the server handles mail for. Each domain's **Manage** page has its
DKIM key, catch-all, administrators and quota, the DNS records to publish (also
as a BIND zone download) and live DNS checks. See
[`multi-domain-hosting.md`](/docs/multi-domain-hosting/).

### Aliases

Addresses that deliver to one or more accounts.

### Quarantine

Messages held by the scanner, with Rescan, Restore and Delete.

### Queue

The outbound mail queue: pending and failed messages, with retry and drop
controls.

### Cluster

Raft state: leader, followers, log index and the health of each node.

### Logs

A live log viewer, filtered by level (debug, info, warn, error) and component
(smtp, imap, raft, web, queue, gossip, blob). Lines arrive over Server-Sent
Events.

---

## Step 7: Import Your Own Mail

Bongo includes `bongo-import` for bringing in mail from other systems.

### Import from .mbox files

```bash
./bin/bongo-import mbox /path/to/export.mbox \
  --dst-user admin@localhost \
  --dst-pass admin
```

### Import from .eml files

```bash
./bin/bongo-import eml /path/to/messages/ \
  --dst-user admin@localhost \
  --dst-pass admin
```

### Import from Maildir

```bash
./bin/bongo-import maildir /path/to/Maildir \
  --dst-user admin@localhost \
  --dst-pass admin
```

### Import from Thunderbird

Auto-discovers Thunderbird local folders:

```bash
./bin/bongo-import thunderbird \
  --dst-user admin@localhost \
  --dst-pass admin
```

### Import everything from a directory

Recursively scans for `.mbox`, `.eml`, `.vcf`, and `.ics` files:

```bash
./bin/bongo-import directory /path/to/mail-export/ \
  --dst-user admin@localhost \
  --dst-pass admin
```

### Import from another IMAP server

Migrate from any IMAP server (Gmail, Outlook, Dovecot, etc.):

```bash
./bin/bongo-import imap \
  --src-host imap.gmail.com \
  --src-port 993 \
  --src-tls \
  --src-user you@gmail.com \
  --src-pass "your-app-password" \
  --dst-user admin@localhost \
  --dst-pass admin
```

All import commands support `--dry-run` to preview without writing, and `--state`
for resumable imports on large mailboxes.

---

## Step 8: Connect a Desktop Mail Client

Bongo works with any standard IMAP/SMTP mail client.

### Thunderbird

1. Open Thunderbird → Account Settings → Add Mail Account
2. Enter: Name: `Admin`, Email: `admin@localhost`, Password: `admin`
3. Click **Configure manually**:
   - **Incoming (IMAP):** Server `127.0.0.1`, Port `1143`, SSL: None, Auth: Normal password
   - **Outgoing (SMTP):** Server `127.0.0.1`, Port `2587`, SSL: None, Auth: Normal password
4. Click Done (accept certificate warnings)

### Apple Mail

1. System Settings → Internet Accounts → Add Other Account → Mail Account
2. Enter: Name: `Admin`, Email: `admin@localhost`, Password: `admin`
3. When asked for server details:
   - **Incoming:** `127.0.0.1`, Port `1143`, no SSL
   - **Outgoing:** `127.0.0.1`, Port `2587`, no SSL

### Generic IMAP Client

- IMAP server: `127.0.0.1:1143` (or `:1993` for TLS)
- SMTP server: `127.0.0.1:2587`
- Username: `admin@localhost`
- Password: `admin`
- Authentication: PLAIN

---

## Step 9: Run the Validation Suite

Bongo ships with a comprehensive validation script that exercises every subsystem
end-to-end: user creation, SMTP delivery, IMAP operations, POP3 retrieval,
contacts round-trip, calendar round-trip, antispam scoring, and web auth.

```bash
make validate
```

The script creates three test users (alice, bob, charlie), sends mail through
SMTP, verifies delivery via IMAP (threading, attachments, HTML), tests POP3
retrieval, creates and round-trips contacts and calendar events, tests antispam
scoring (sends a spam-like message and verifies it lands in Junk), and checks
web authentication flows.

Output shows per-check pass/fail status. At the end you'll see a summary:

```
====================================================
  Bongo Server Validation Report
  ---------------------------------------------------
  TOTAL: N/N checks passed                      PASS
====================================================
```

---

## Step 10: Send a Test Email

You can send a quick test email without any special tools:

### Using swaks

```bash
swaks --to admin@localhost \
      --from sender@example.com \
      --server 127.0.0.1:2525 \
      --header "Subject: Hello from swaks" \
      --body "This is a test message sent via SMTP."
```

### Using Go stdlib

```go
package main

import "net/smtp"

func main() {
    msg := []byte("Subject: Test from Go\r\n\r\nHello, Bongo!\r\n")
    smtp.SendMail("127.0.0.1:2525", nil,
        "sender@example.com", []string{"admin@localhost"}, msg)
}
```

Save as `send.go` and run with `go run send.go`.

---

## Step 11: Explore the Antispam System

Bongo has a built-in antispam pipeline with two layers:

**Rule-based scorer** — Checks for missing headers, SPF/DKIM failures, and
28 common spam phrases. Each check adds points; messages scoring above 0.5
(on a 0-1 scale) are automatically routed to the Junk folder.

**Bayesian filter** — Per-user machine learning classifier. When you move a
message to Junk (or mark it as spam), Bongo trains the Bayesian model for your
account. Over time, the filter learns your personal spam patterns.

To test antispam scoring, send a suspicious message:

```bash
swaks --to admin@localhost \
      --from spammer@example.com \
      --server 127.0.0.1:2525 \
      --header "Subject: " \
      --body "CLICK HERE to ACT NOW! FREE MONEY! LIMITED TIME OFFER!"
```

This message will score high (empty subject + spam phrases) and should land in
the Junk folder instead of the Inbox.

---

## Architecture Overview

Bongo is a single binary that includes:

- **SMTP server** — Inbound (port 25/2525) and submission (port 587/2587) with
  DKIM signing, SPF checking, and antispam scoring
- **IMAP server** — Full IMAP4rev1 with IDLE push, search, flags, and folders
- **POP3 server** — For clients that prefer POP3
- **CalDAV/CardDAV** — Standards-compliant calendar and contact sync
- **HTMX Web UI** — Server-rendered HTML with Alpine.js interactivity and HTMX
  for SPA-like navigation without a JavaScript framework
- **Raft consensus** — Built-in clustering for high availability (three or five
  `server` nodes form a quorum)
- **Embedded storage** — PebbleDB (key-value) + content-addressed blob store.
  No external database required.
- **Admin panel** — User and domain management, quarantine, queue monitoring,
  real-time logs, cluster status

---

## Useful Commands

```bash
make build      # templ generate + build bin/bongo and bin/bongo-import
make dev        # build, start a dev server, validate, seed, keep running
make run        # build and start a dev server
make seed       # seed test data into a running dev server
make validate   # run the validation suite against a running dev server
make test       # unit tests
make test-all   # unit and integration tests
make ui-shots OUT=~/shots   # screenshot every route (light, dark, mobile)

# Import mail from a directory
./bin/bongo-import directory /path/to/data \
  --dst-user admin@localhost --dst-pass admin

# Check server health
curl http://localhost:8080/health/ready
```

---

## Troubleshooting

### Setup and development

**Certificate warning in a mail client**
Dev mode's TLS ports (IMAPS 1993, POP3S 1995) use a self-signed certificate.
Accept it in the client, or use the plain ports 1143 and 1110.

**Port already in use**
Another process is using one of Bongo's ports. Check with `lsof -i :8080` (or
whichever port) and stop the conflicting process.

**`templ generate` shows `updates=0`**
The templ compiler uses content hashing, not timestamps. If the generated
`_templ.go` files already match, it won't regenerate. This is normal.

**Mail client can't connect**
Make sure you're connecting to the plain (non-TLS) IMAP port `1143`, not the
TLS port `1993`. For SMTP, use submission port `2587` with authentication.

**Antispam is too aggressive / not aggressive enough**
The default spam threshold is 0.5. Over time, the Bayesian filter will learn
from your spam/ham classifications. You can also check the rule-based scorer
in `internal/antispam/scorer.go` to adjust phrase weights.

### Outbound mail troubleshooting

This section covers problems where mail your server sends is not reaching
recipients or is being filed as spam. For help diagnosing these, see
[Multi-domain hosting: Reading the DNS status checks](/docs/multi-domain-hosting/#reading-the-dns-status-checks)
for live DNS verification and the sections below for message-inspection techniques.

#### Outbound mail rejected by the receiver

**Symptom:** Recipients never receive mail from your server. The admin panel's
Queue shows messages with permanent delivery failures. Logs show:

```
msg="relay: permanent recipient failure" error="504 \"5.5.2 <localhost>: Helo command rejected: need fully-qualified hostname\""
```

Or similar 5.5.2 (protocol syntax) errors at the RCPT stage. Messages fail
immediately without retry.

**Cause:** Your `smtp.hostname` is not set to a fully-qualified domain name,
or has not been configured at all. Most large mail providers (Gmail, Outlook,
Postfix with `reject_non_fqdn_helo_hostname`) enforce RFC 5321 section 4.1.1.1
and reject mail from servers that do not present a qualified name in the HELO
command. When `smtp.hostname` is missing or unqualified, Bongo falls back to
an IP address literal (e.g. `[192.0.2.1]`), which these receivers refuse.

**Check and fix:**

1. Look at the server startup logs. If `smtp.hostname` is not set or not
   qualified, you will see:

   ```
   relay: no fully-qualified HELO name could be derived; outbound mail will
   use an address literal instead, which many strict receivers reject -- set
   smtp.hostname to your public mail hostname
   ```

2. Set `smtp.hostname` in your configuration to your public mail hostname.
   This should match your reverse DNS (PTR) record and ideally be the same as
   your mail server's A record hostname. Example:

   ```hcl
   smtp {
     hostname = "mail.example.com"
   }
   ```

3. Restart Bongo. On startup, if the hostname is now qualified, the warning
   will not appear.

4. Send a test message to an external provider and verify delivery.

#### Bounce notifications land in junk instead of the inbox

**Symptom:** When a message bounces (permanent delivery failure), the bounce
notification email lands in Junk instead of the Inbox. Users do not see that
their messages failed.

**Cause:** A bounce (Delivery Status Notification, RFC 3464) is an email from
the server itself. For the bounce to avoid spam filters and reach the Inbox,
it must be digitally signed with DKIM and the signature must verify at the
recipient's mail server. If your server's DKIM public key is not published in
DNS, bounces fail DMARC authentication and are treated as spam.

**Check and fix:**

1. Go to the admin panel: **Admin → Domains** and click **Manage** next to
   the domain whose bounces are not arriving.

2. Look at the **DNS Configuration** section. Find the **DKIM** row. It should
   show one of:

   - **Valid** — the published TXT record matches your server's key. Bounces
     should verify correctly.
   - **Missing** — no matching DKIM TXT record is published. This is why bounces
     are failing.
   - **Not generated** — you have not yet generated a DKIM key for this domain.

3. If the status is Missing or Not generated:

   - Go to **DKIM Signing** and click **Generate DKIM Key** if no key exists.
   - Copy the exact TXT record shown (selector `mail`, domain `mail._domainkey.<your-domain>`)
     and publish it at your DNS provider.
   - Wait for DNS propagation (usually a few minutes, but depends on your TTL).
   - Reload the Manage page — the DKIM status should turn Valid.

4. If you see this warning in the logs when a bounce is generated:

   ```
   bounce: no DKIM signer for domain, delivering unsigned
   ```

   It means the domain still has no registered signer. Generate a key (step 3 above).

5. Send a test message that will bounce (e.g. to a non-existent user) and
   verify that the bounce arrives in the user's Inbox, not Junk. Inspect the
   bounce's headers (see below) to confirm DKIM passed.

#### How to see why a message was filed as spam

**Symptom:** A message landed in Junk but you do not know why. You need to
inspect the spam scoring decision and authentication results.

**Solution:** Open the message and choose **More > View Original**. It renders the
full RFC 5322 raw source including all headers. Look for these headers:

- **`Authentication-Results`** — records the SPF, DKIM and DMARC verdicts
  from when the message arrived. Format:
  ```
  Authentication-Results: mail.example.com; spf=pass; dkim=pass header.d=sender.com; dmarc=pass
  ```
  Values are one of: `pass`, `fail`, `softfail`, `neutral`, `none`, `temperror`.

- **`X-Spam-Score`** — the numerical score assigned by Bongo's antispam
  pipeline. Higher = more spam-like. Example:
  ```
  X-Spam-Score: 0.62
  ```

- **`X-Spam-Status`** — `Yes` if the score exceeded the threshold (0.5 by
  default), `No` otherwise:
  ```
  X-Spam-Status: Yes
  ```

- **`X-Spam-Reasons`** — comma-separated list of the rules that contributed to
  the score. Examples:
  ```
  X-Spam-Reasons: Missing From header, SPF softfail, No Subject line
  ```

If SPF or DKIM failed, check the sections above to ensure DNS records are
published and match your server's configuration. If DMARC failed, check that
sender alignment (DKIM or SPF signing domain must match the From: header
domain) is correct.

#### Mail rejected for IP reputation (RBL listing)

**Symptom:** Outbound mail is rejected at one or more recipients with a
message naming a blocklist. Logs show:

```
msg="relay: MX attempt failed, trying next" error="closing data: 554 \"5.7.1 Service unavailable; Client host [192.0.2.1] blocked using b.barracudacentral.org\""
```

The rejection happens during the DATA phase, after EHLO, MAIL FROM and RCPT TO
all succeeded. **Where it fails is the diagnostic.** A rejection at `closing
data` means the protocol side of your server is fine and only the sending IP's
reputation is at issue. Contrast that with the HELO problem above, which fails
earlier, at the RCPT stage.

Bongo tries the recipient's remaining MX hosts first, and if they all refuse,
the message stays queued and is retried with backoff rather than being
discarded. It is only bounced back to the sender once retries are exhausted,
so a listing that clears within a day or two may resolve itself without the
sender ever seeing a failure.

**What this means:** Your server's outbound IP address has been listed on a
reputation blocklist (RBL) maintained by the organisation named in the error
(Barracuda, Spamhaus, SpamCop, etc.). Receivers that consult that blocklist
refuse the message at the final DATA phase.

This is **not** a problem with your server's configuration — it is a reputation
issue with the IP address itself. Brand-new servers, especially those on cloud
VPS ranges, often start with inherited listings because:

- Cloud providers recycle IP addresses and blocklists track the address, not
  the owner. A previous tenant's spam activity caused the listing.
- A large netblock may be listed, affecting all IPs in that range regardless
  of their individual behaviour.
- Slow delisting means even after you stop any spam, the IP may remain listed
  for days or weeks.

**Check and fix:**

1. **Verify the IP and which blocklist rejected it.** The error message above
   names `b.barracudacentral.org`. Note your server's outbound IP address
   (the one on your MX record's A address).

2. **Query the blocklist.** Reverse the IP octets and query the zone named in
   the rejection. For example, if your IP is `192.0.2.1` and the blocklist is
   `b.barracudacentral.org`:

   ```bash
   dig 1.2.0.192.b.barracudacentral.org A
   ```

   - If you see an answer like `127.0.0.x` (any value in the 127.0.0.0/24
     range), you are listed.
   - If you see `NXDOMAIN`, you are not listed on that blocklist.

3. **Check other major blocklists** even if one query succeeds. Being listed
   on one blocklist while clean on others is common and only affects receivers
   that consult that specific list:

   ```bash
   dig 1.2.0.192.zen.spamhaus.org A          # Spamhaus Zen
   dig 1.2.0.192.b.barracudacentral.org A    # Barracuda
   dig 1.2.0.192.bl.spamcop.net A            # SpamCop
   ```

4. **Check alignment of reverse DNS, HELO name and authentication.**
   Delisting requests are more likely to succeed when your server's
   configuration is clean:

   - Check your PTR (reverse DNS) record:
     ```bash
     dig -x 192.0.2.1
     ```
     It should resolve to your mail hostname (e.g. `mail.example.com`).

   - Verify `smtp.hostname` in your config matches the PTR and your MX's A
     record. They should all resolve to the same IP.

   - Check that SPF, DKIM and DMARC are aligned (see
     [Multi-domain hosting](/docs/multi-domain-hosting/#5-verify-spf-and-dmarc)
     for details).

5. **Request delisting** from the blocklist operator. Most blocklists have a
   web form (e.g. `barracudacentral.org/lookup`, `spamhaus.org/query/lookup`).
   Include your IP, the domain(s) you are sending from, and evidence that your
   server is legitimate: screenshots of SPF/DKIM/DMARC passes, your DNS
   configuration, and a brief explanation of your mail source. Requests are
   processed faster when alignment is clean.

6. **Do not hold up mail waiting for delisting.** If a specific recipient's
   blocklist is causing frequent rejections, consider using a third-party
   smarthost relay (e.g. Mailgun, SendGrid, AWS SES) for outbound mail until
   the listing is cleared. Configure `smtp.relay.host` to route through a
   relay server instead:

   ```hcl
   smtp {
     relay {
       enabled = true
       host    = "smtp.relay.example.com"
       port    = 587
       # ... auth credentials as needed
     }
   }
   ```

   Restarting Bongo will begin using the relay immediately.

#### Mail storage growing faster than expected

**Symptom:** The blob store grows at roughly twice the rate you would expect
from the volume of mail received.

**Cause:** Delivery stamps `Authentication-Results` and `X-Spam-*` headers onto
each message (see [How to see why a message was filed as
spam](#how-to-see-why-a-message-was-filed-as-spam)). That changes the message
bytes, so the stored copy is written as a new blob and the one written at SMTP
DATA time is left unreferenced. The unreferenced-blob collector reclaims those
originals, but it is **off by default** — it deletes data, so it is opt-in
rather than something that starts on its own.

With it off, every delivered message keeps two full copies indefinitely.

**Check and fix:**

1. Look for sweep activity in the logs. If the collector is running you will
   see entries like:

   ```
   msg="blob-gc: swept orphaned blobs" candidates=3 deleted=3 dry_run=false
   ```

   No such entries means it has never run.

2. Enable it in your configuration, starting with `dryrun` so you can see what
   it would remove before anything is deleted:

   ```hcl
   storage {
     blob_gc = "dryrun"
   }
   ```

3. Restart Bongo and watch for `dry_run=true` sweep entries. Once the
   candidates look right, switch to `blob_gc = "on"` and restart again.

The sweep only deletes blobs that have been unreferenced across two consecutive
passes and are older than a minimum age, so a blob still in flight is never
collected.
{% endraw %}
