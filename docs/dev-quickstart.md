---
layout: doc
title: "Dev Mode Quick Start"
nav_title: "Development quick start"
permalink: /docs/dev-quickstart/
source: https://github.com/bongo-project/bongo/blob/main/docs/dev-quickstart.md
---
{% raw %}
# Dev Mode Quick Start

## Build and Run

```bash
make dev
```

`make dev` generates the templates, builds `bin/bongo` and `bin/bongo-import`,
starts a dev server, runs the validation suite, seeds test data
and keeps the server running until Ctrl-C. The web UI is at
<http://localhost:8080>.

To run the server by hand:

```bash
make build
./bin/bongo serve --dev
```

Dev mode starts a single-node server with ephemeral storage (deleted on
shutdown) and needs no configuration. The web UI is always plain HTTP in dev
mode; the IMAPS and POP3S ports use a self-signed certificate.

Static assets are cache-busted by commit hash. After rebuilding from a new
commit, reload open tabs to pick up changed JavaScript and CSS.

## Default Ports

| Service    | Port | Protocol                 |
|------------|------|--------------------------|
| HTTP       | 8080 | Web UI, health           |
| Control    | 8081 | /internal, loopback only |
| SMTP MX    | 2525 | Inbound mail             |
| SMTP Sub   | 2587 | Submission (auth)        |
| SMTPS Sub  | 2465 | Submission, implicit TLS |
| IMAP       | 1143 | Plaintext/STARTTLS       |
| IMAPS      | 1993 | Implicit TLS             |
| POP3       | 1110 | Plaintext/STARTTLS       |
| POP3S      | 1995 | Implicit TLS             |

## Test User

Dev mode creates a test user on startup:

- **Email:** `admin@localhost`
- **Password:** `admin`

## Test Data

`make dev` seeds already. Against a dev server started by hand:

```bash
make seed
```

The seed creates the users `alice`, `bob` and `charlie` (`@localhost`),
messages, subfolders, contacts and calendar events. Running it twice creates
duplicate contacts and events.

## Send a Test Email

Using [swaks](https://github.com/jetmore/swaks):

```bash
swaks --to admin@localhost \
      --from sender@example.com \
      --server 127.0.0.1:2525 \
      --header "Subject: Hello from swaks" \
      --body "This is a test message."
```

Or with Go's `net/smtp`, saved as `send.go` and run with `go run send.go`:

```go
package main

import "net/smtp"

func main() {
	smtp.SendMail("127.0.0.1:2525", nil, "sender@example.com",
		[]string{"admin@localhost"}, []byte("Subject: Test\r\n\r\nHello"))
}
```

## Connect Thunderbird

1. Open Thunderbird, go to **Account Settings > Account Actions > Add Mail Account**.
2. Enter:
   - Name: `Admin`
   - Email: `admin@localhost`
   - Password: `admin`
3. Click **Configure manually** and set:
   - **Incoming (IMAP):**
     - Server: `127.0.0.1`
     - Port: `1143`
     - SSL: None
     - Authentication: Normal password
   - **Outgoing (SMTP):**
     - Server: `127.0.0.1`
     - Port: `2587`
     - SSL: None
     - Authentication: Normal password
4. Click **Done** (accept any certificate warnings for self-signed certs).

## Screenshot Every Route

`make ui-shots` builds the server into a temporary directory, starts a dev
server on free ports, seeds it, logs in and captures each main route at
1440x900 light, 1440x900 dark and 390x844 light with headless Chrome. It reports
console errors, CSP violations and failed same-origin requests.

```bash
make ui-shots                 # screenshots go to a new temp dir
make ui-shots OUT=~/shots     # OUT must be outside the repository
go run ./scripts/ui-shots -out ~/shots -timeout 30s -chrome /path/to/chrome
```

It needs a local Chrome or Chromium and never downloads one. Exit status is 0
when every capture is clean, 1 when a route has errors, and 2 when setup
failed; through `make` any failure shows as make's exit status 2, so read the
output. It is not run in CI.

## Verify

Check the health endpoint:

```bash
curl http://127.0.0.1:8080/health/ready
```

Returns `{"status":"ready"}` when the server is fully initialised.
{% endraw %}
