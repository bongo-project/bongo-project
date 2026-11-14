---
layout: doc
title: "Load test: first run (preliminary)"
permalink: /load-test/
---

# Load test: first run (preliminary)

The Bongo project ran its load test on two rented virtual machines from
8 to 13 November 2026. The run found which part of the server reaches its
limit first. It does not give publishable capacity figures.

## Status of these numbers

The numbers on this page are preliminary.

- Each stage ran once. A headline figure needs two runs that agree within 10%.
- The stages ran on four releases, from v0.15.3 to v0.15.12. Fixes went in
  between stages.
- Antivirus scanning was off in every stage. Antispam was on.

Headline figures will come from a final run on one tagged release, on the same
kind of shared-vCPU machine, repeated twice. Most installations run on a VM or in
a container. A run on dedicated hardware is the last test of the series and is
reported separately.

## Setup

| | |
|---|---|
| Server | Hetzner cx23: 2 shared vCPU (x86), 4 GB RAM, no swap |
| Disk | Local disk for the account and connection stages; 100 GB network volume for the storage, soak and failure stages |
| Load generator | A second cx23 on a private network |
| Bongo | v0.15.3 to v0.15.12 |
| Config | `deploy/loadtest.example.hcl`: antispam on, antivirus off, outbound mail to a test sink |
| Test domain | `bongo.test` (reserved by RFC 6761) |

Traffic model: 50% of accounts hold an IMAP IDLE connection, 5% run an IMAP
fetch and flag cycle every 30 seconds, 2% use CalDAV and CardDAV every 60
seconds, 1% use POP3 every 60 seconds. Test messages are 8 KB unless stated. A
probe sends a message every 5 seconds and measures delivery and search delay.

## Findings

The first limit in every stage was CPU. Two kinds of work used it: search
indexing of new mail, and password checks (bcrypt) at login.

| Measure | Result | Conditions |
|---|---|---|
| Registered accounts held | 10,000, for 15 hours, no mail lost | About 820 connected clients, 3 messages per second, 200 active mailboxes |
| Sustained message rate | About 3 to 4 messages per second | 10,000 accounts, about 820 clients |
| Delivery with no clients | About 16 messages per second | 1,500 accounts; search indexing was the limit |
| Active users | About 3,000 accounts with 58% connected (1,740 clients), no errors | 5 messages per second; at 6,000 accounts logins took 16.8 seconds |
| Open IMAP connections | 15,000 held for 25 minutes at 9.5% CPU | About 100 KB of memory each |
| New logins | About 16 per second | TLS handshake plus bcrypt |
| Memory | About 1 GB resident | 10,000 accounts, about 820 clients, 24.5-hour soak; no growth |
| Disk | About 85 KB of search index per message | Most of the data directory is search index |

Registered accounts and connected clients are separate figures. A server holds
far more accounts than it has users connected at once.

## Failure cases

| Case | Result |
|---|---|
| Restart under load | Mail protocols back 2.8 seconds after start, web interface after 43 seconds; no accepted message lost; all IDLE clients reconnected |
| Disk below the free-space threshold, then full, for 15 minutes | SMTP answered with a temporary error (452) during the window and accepted mail again within 1 second of space returning; no accepted message lost; no crash |
| Outbound relay down for 30 minutes | 2,250 messages submitted, each delivered once after the relay returned; no bounces |
| Unclean stop | Every index rebuilt at the next start: 68 minutes for 10,000 accounts, with no listener open |

## What broke, and the fixes

| Fixed in | Problem |
|---|---|
| v0.15.5 | The delivery spool kept every delivered envelope, so deleted mail's storage was never freed |
| v0.15.10 | Accepted mail could be set aside after a slow write instead of delivered |
| v0.15.10 | Every start restored the full snapshot and rebuilt all indexes (28 minutes at 75,000 messages) |
| v0.15.11 | Stop waited for open web connections and was killed, which forced an index rebuild at the next start |
| v0.15.12 | The spool delivered messages in random order instead of arrival order |
| v0.15.13 | The queue's "oldest pending" figure showed the next message due, not the oldest |
| v0.15.13 | A line over the SMTP length limit got a temporary error, so senders retried it for days |

The compose template's memory limit was raised from 512 MB to 2 GB.

## Not measured in this run

- The effect of antivirus scanning.
- How the limits move with more CPU, or on dedicated hardware.
- Backup, start and garbage-collection times above 75,000 messages.

## Repeating the run

The load tool is `scripts/loadgen` in the
[source repository](https://github.com/bongo-project/bongo). The runbook is
[docs/load-testing.md](https://github.com/bongo-project/bongo/blob/main/docs/load-testing.md),
and the full stage-by-stage results are in
[docs/design/load-test-results.md](https://github.com/bongo-project/bongo/blob/main/docs/design/load-test-results.md).

No other mail server was tested, so this page makes no comparison.
