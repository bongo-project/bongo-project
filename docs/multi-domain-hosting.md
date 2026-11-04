---
layout: doc
title: "Multi-domain hosting"
nav_title: "Multi-domain hosting"
permalink: /docs/multi-domain-hosting/
source: https://github.com/bongo-project/bongo/blob/main/docs/multi-domain-hosting.md
---
{% raw %}
# Multi-domain hosting

Bongo hosts many mail domains on a single server. Every tenant domain shares
one mail hostname, one TLS certificate and one set of listeners; each domain then
gets its own DKIM key, catch-all, administrators and quota. This guide takes you
from a running server to a fully configured tenant domain.

It assumes you already have a working single-node deployment (see
[`deploy/README.md`](https://github.com/bongo-project/bongo/blob/main/deploy/README.md)). The examples use `mail.example.com`
as the shared mail hostname and `tenant.com` as a domain you are adding.

## The shared-host model (read this first)

There is one mail hostname for the whole server, set once in config as
`smtp.hostname`:

```hcl
smtp {
  hostname = "mail.example.com"
}
```

Every domain you host points its MX and service records at **that** hostname —
not at per-domain names. So `tenant.com` and `another.com` both have
`MX -> mail.example.com`. This is why one certificate and one set of DNS service
records cover every tenant: clients always resolve to, connect to and validate
the same host. You do not add a domain in the HCL file; domains are created at
runtime through the admin UI and stored in the cluster.

Consequences worth knowing up front:

- One TLS certificate (for `mail.example.com`) secures SMTP, IMAP and the web UI
  for all tenants.
- A tenant only needs A/AAAA records for the apex and a couple of client-discovery
  names; the mail itself always flows through `mail.example.com`.
- Outbound mail for every domain leaves as `mail.example.com`, so that host needs
  correct forward and reverse DNS (PTR) and its own SPF/DKIM alignment.

## 1. Add the domain

As a global administrator, go to **Admin → Domains** (`/admin/domains`) and add
`tenant.com`. Only a global admin can create or delete a domain; once it exists,
you can delegate day-to-day management (see step 7).

A new domain starts **enabled**. You can disable it at any time from its Manage
page. A disabled domain refuses all inbound mail (SMTP answers `550 5.1.1`
for every address on it, including aliases and the catch-all) without being
deleted; its accounts and stored mail are kept, and re-enabling restores
delivery.

## 2. Open the domain's Manage page

Click **Manage** next to the domain (`/admin/domains/tenant.com`). This page is
the control centre for everything below: live DNS status, the record set to
publish, DKIM, catch-all, administrators, owner and quota. It performs live DNS
lookups each time you load it, so it doubles as your verification tool.

## 3. Publish DNS

The **DNS Setup Records** section lists exactly what to publish at the tenant's
DNS provider, generated for *this* server so the values never drift from what the
status checks expect. Copy each row, or use **Download BIND zone file** to get
them all at once (`/admin/domains/tenant.com/dns.zone`).

The record set is:

| Type | Host | Value | Purpose |
|------|------|-------|---------|
| A | `@`, `mail`, `autoconfig`, `autodiscover` | server IPv4 address | apex + client-discovery names |
| AAAA | `@`, `mail` | server IPv6 address | only when the mail host has an IPv6 address |
| MX | `@` | `10 mail.example.com.` | route inbound mail to the shared host |
| TXT (SPF) | `@` | `v=spf1 mx ~all` | authorise the MX host to send |
| TXT (DMARC) | `_dmarc` | `v=DMARC1; p=none; rua=mailto:postmaster@tenant.com` | reporting, policy `none` to start |
| TXT (DKIM) | `mail._domainkey` | `v=DKIM1; k=rsa; p=...` | shown only after you generate a key (step 4) |
| SRV | `_imaps._tcp`, `_submissions._tcp` (465), `_submission._tcp` (587), `_autodiscover._tcp`, `_caldavs._tcp`, `_carddavs._tcp` | target `mail.example.com.` | RFC 6186 client autodiscovery |
| TXT | `_caldavs._tcp`, `_carddavs._tcp` | `path=/caldav/`, `path=/carddav/` | CalDAV/CardDAV discovery path |

Start DMARC at `p=none` so you can watch the `rua` reports before you enforce.
Move to `p=quarantine` and then `p=reject` once SPF and DKIM are consistently
passing.

If a tenant domain's website is served by something other than Bongo, that
web server should also redirect `/.well-known/caldav` and
`/.well-known/carddav` to the mail host for every HTTP method; Apple tries
the email domain first. See [`caldav-carddav.md`](/docs/caldav-carddav/).

### Reading the DNS status checks

The **DNS Configuration** section shows the live state of each record against
what this server expects. The legend below the table explains the four states:

- **Valid** — the record is published and matches this server.
- **Missing** — no matching record was found; publish it using the setup records
  above. For MX, Valid means at least one MX host name equals
  `mail.example.com`; a domain whose MX records all point elsewhere reads as
  Missing.
- **Not generated** — nothing to check yet, e.g. no DKIM key exists.
- **Could not check** — the DNS lookup failed or timed out; retry shortly.

DNS changes take as long as your TTLs to propagate. If a record reads Missing
straight after publishing, give it time and reload.

## 4. Generate the DKIM key

In **DKIM Signing**, click **Generate DKIM Key**. Bongo creates a per-domain
RSA-2048 key with selector `mail`, stores the private key in the cluster and
starts signing outbound mail from `tenant.com` immediately. The page then shows
the exact `mail._domainkey.tenant.com` TXT record to publish.

Publish that record, then reload the Manage page — the DKIM check should turn
Valid once DNS propagates. **Rotating** a key follows the same flow, but note:
mail signed with the new key will not verify until the new TXT record has
propagated, so publish it promptly after rotating.

## 5. Verify SPF and DMARC

With SPF (`v=spf1 mx ~all`), DKIM published and DMARC in place, send a test
message from a `tenant.com` account to an external provider (Gmail is convenient —
"Show original" reports SPF, DKIM and DMARC results). You want SPF `pass`, DKIM
`pass` aligned to `tenant.com`, and DMARC `pass`. The Manage page's status checks
should show all four rows Valid.

Forwarding: mail a user forwards (account forward address or a rule) leaves with an SRS
envelope sender on that user's own domain, so SPF at the next hop checks `tenant.com`, not
the original author's domain. `tenant.com`'s SPF record must therefore include this host.
A user whose profile address is not on a hosted domain keeps the original sender, and the
forward fails SPF at the next hop.

## 6. Set a catch-all (optional)

**Catch-All Address** routes any mail to an unrecognised address in the domain to one
user. Enter the owning user's ID; clear it to turn catch-all off. Use this
sparingly — a catch-all receives spam addressed to guessed local parts.

## 7. Delegate administration

Bongo has two admin tiers:

- **Domain owner** — set in the **Domain Owner** section (global-admin only). The owner
  has elevated trust for the domain and is implicitly a domain administrator.
- **Domain administrators** — granted in the **Domain Administrators** section.
  They can manage users, aliases, DKIM and catch-all *for this domain only*.

Tenancy isolation is enforced server-side: a domain admin only ever sees and acts
on their own domains. Requests for a domain they do not administer return 403,
and they cannot enumerate users outside their domains. Creating and deleting
domains, setting the owner and setting quotas remain global-admin actions.

## 8. Set per-domain quotas

In **Quota** (global-admin only) you can cap a domain:

- **Max users** — the number of accounts whose primary domain is this domain
  (`0` = unlimited). Enforced when a new user is created.
- **Max storage** — aggregate stored-message bytes for the domain (`0` =
  unlimited). Checked at SMTP delivery, IMAP APPEND, CalDAV/CardDAV PUT and web
  saves: once the domain is at or over quota those writes are refused. Usage is
  recomputed by the leader about every ten minutes, so this is a soft limit
  that can be overshot between recomputations.

## 9. Client autoconfiguration

Once the A records for `autoconfig.tenant.com` / `autodiscover.tenant.com` and
the SRV records are published, mail clients set themselves up from just an
address and password. Bongo serves:

- **Thunderbird / Mozilla** — `https://autoconfig.tenant.com/.well-known/autoconfig/mail/config-v1.1.xml`
- **Outlook** — `https://autodiscover.tenant.com/autodiscover/autodiscover.xml`
- **Apple Mail (iOS/macOS)** — `https://mail.example.com/.well-known/mobileconfig`

All of them advertise the shared host `mail.example.com` with IMAPS on 993 and
submission on 465 (implicit TLS) first, then 587 (STARTTLS). The Apple profile
carries a single outgoing server, so it uses 465. When `smtp.submissions_port`
is 0, or no `smtp.tls` certificate is configured, 465 is left out of all three. In production, bongo only answers autoconfig for domains it
actually hosts, so a domain must exist (and be enabled) before autoconfig works
for it.

## Checklist

For each domain you host:

- [ ] Domain created in **Admin → Domains**
- [ ] A/AAAA, MX, SPF, DMARC and SRV records published (from the setup records)
- [ ] DKIM key generated and its TXT record published
- [ ] All four DNS status checks show **Valid**
- [ ] Test message to an external provider shows SPF/DKIM/DMARC `pass`
- [ ] Owner and/or domain administrators delegated (if handing off)
- [ ] Quota set (if the domain should be capped)
- [ ] A test client configured via autoconfig

## See also

- [`deploy/README.md`](https://github.com/bongo-project/bongo/blob/main/deploy/README.md) — standing up the single server
- [`docs/multi-node-cluster-checklist.md`](/docs/multi-node-cluster-checklist/) —
  hardening before you scale beyond one node
{% endraw %}
