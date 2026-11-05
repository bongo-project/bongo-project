---
layout: doc
title: "CalDAV and CardDAV"
nav_title: "CalDAV and CardDAV"
permalink: /docs/caldav-carddav/
source: https://github.com/bongo-project/bongo/blob/main/docs/caldav-carddav.md
---
{% raw %}
# CalDAV and CardDAV

Bongo serves calendars and tasks over CalDAV and contacts over CardDAV on its
web listener (HTTPS, port 443 in a normal install). This page covers account
details, how clients find the server, client setup, what syncs, and how to
check a connection that fails.

## Account details

| Field | Value |
|-------|-------|
| Server | The mail host name, for example `mail.example.com` |
| User name | The full email address, for example `alice@example.com`. The local part alone is refused. |
| Password | The account password |
| CalDAV path | `/caldav/` |
| CardDAV path | `/carddav/` |
| Port and security | 443 with TLS |

Clients authenticate with HTTP Basic auth over TLS. Two-factor authentication
does not apply to CalDAV and CardDAV: the account password alone signs in
(see `SECURITY.md`). Repeated failed logins from one address are throttled;
the server answers `429 Too Many Requests` until the lockout expires.

A disabled account and a resource account (room or equipment) cannot sign
in. Both get the same `401` as a wrong password.

## How clients find the server

Clients look for the server in this order (RFC 6764). Apple, Thunderbird and
DAVx5 each use some of these steps.

1. **DNS SRV and TXT records** on the email domain. With these, a client that
   is given only an email address finds the host and the path. The admin
   DNS guide (Admin, Domains, DNS) lists them for each hosted domain:

   ```
   _caldavs._tcp.example.com.   SRV 0 1 443 mail.example.com.
   _carddavs._tcp.example.com.  SRV 0 1 443 mail.example.com.
   _caldavs._tcp.example.com.   TXT "path=/caldav/"
   _carddavs._tcp.example.com.  TXT "path=/carddav/"
   ```

2. **`/.well-known/caldav` and `/.well-known/carddav`** on the host the
   client tries. Bongo redirects both paths, for every HTTP method, to
   `/caldav/` and `/carddav/` with `301`. Clients send `PROPFIND` first, so a
   redirect for `GET` alone is not enough. Versions up to 0.14.1 redirected
   `GET` only and answered `PROPFIND` with `405`; on those versions, enter
   the server path by hand (see Client setup).

3. **The email domain's website.** Apple tries
   `https://<email domain>/.well-known/caldav` when the user enters only an
   email address. If the domain's website is not served by Bongo, that web
   server must redirect both well-known paths to the mail host, for every
   method including `PROPFIND` and `OPTIONS`:

   ```
   /.well-known/caldav  -> https://mail.example.com/caldav/
   /.well-known/carddav -> https://mail.example.com/carddav/
   ```

   A `301`, `302`, `307` or `308` redirect works. A static file does not.

Once the client reaches `/caldav/` or `/carddav/` and signs in, Bongo
reports the user's principal, calendar home, address book home and
calendar user address set, and the client lists the collections itself.

## Client setup

### macOS Calendar and Contacts

1. System Settings, Internet Accounts, Add Other Account, then CalDAV
   account (or CardDAV account for Contacts).
2. Account type: Manual.
3. User name: the full email address. Password: the account password.
   Server address: the mail host name.
4. If setup fails at "Verifying", choose Advanced and set the server path
   to `/caldav/` (or `/carddav/`), port 443, Use SSL on.

### iOS and iPadOS

Settings, Calendar (or Contacts), Accounts, Add Account, Other, Add CalDAV
Account (or Add CardDAV Account). Enter the mail host name, the full email
address and the password. If verification fails, open Advanced Settings and
set the account URL to `https://mail.example.com/caldav/` (or `/carddav/`).

The configuration profile at `https://mail.example.com/.well-known/mobileconfig`
sets up the mail, CalDAV and CardDAV accounts. It contains no password, so the
device asks for it.

### Thunderbird

Calendar: New Calendar, On the Network, user name the full email address,
location `https://mail.example.com/caldav/`. Thunderbird lists every
calendar on the account, including the Tasks calendar, and offers to
subscribe to each.

Contacts: New Address Book, CardDAV, location
`https://mail.example.com/carddav/`.

### Android with DAVx5

Add an account with "Login with URL and user name". Base URL
`https://mail.example.com/`, user name the full email address. DAVx5 finds
both CalDAV and CardDAV from the base URL. On versions up to 0.14.1 use
`https://mail.example.com/caldav/` as the base URL, and add a second account
with `https://mail.example.com/carddav/` for contacts. Tasks sync to tasks.org or
OpenTasks when one of them is installed.

## What syncs

| Collection | Path | Notes |
|------------|------|-------|
| Calendars | `/caldav/{user}/calendars/{calendar}/` | Events (VEVENT), tasks (VTODO) or both, as set when the calendar was created. A new account's first calendar, Personal, is usually named `default`. |
| Tasks | `/caldav/{user}/calendars/tasks/` | Tasks (VTODO) only. See below for when it exists. |
| Calendars shared with the user | `/caldav/{user}/calendars/shared-{owner}-{calendar}/` | From v0.15.0. Read or read-write, as the owner granted. Writes are stored under the owner and count against the owner's quota. |
| Subscribed calendars | as calendars | Read-only. A `PUT` or `DELETE` of an object inside one answers `403`. A `DELETE` of the collection itself answers `409`: unsubscribe in the web interface. |
| Address book | `/carddav/{user}/addressbooks/default/` | Contacts (vCard). |

From v0.15.0 the server also handles calendar scheduling (RFC 6638). It
sends invitations, updates, cancellations and replies for events saved by a
CalDAV client, and places received invitations in the client's scheduling
inbox. Clients that see the `calendar-auto-schedule` capability stop sending
invitation mail themselves, so each attendee receives one message.

A calendar accepts only the components it is set up for. A `PUT` of a task
into an events calendar, or of an event into a tasks calendar, answers `403`
with the `supported-calendar-component` precondition.

The Tasks calendar (`tasks`) is not created with the account. Bongo creates
it for any account with no calendar that holds tasks (a subscribed calendar
does not count), the next time the account opens a month, week, day, agenda or settings page in
the web interface, saves an event there, or sends a CalDAV listing of
calendars, a `PUT`, an `MKCALENDAR` or an extended `MKCOL`. A first use by an account with no
calendar at all also creates Personal; Personal and Tasks are made first, then
any requested calendar. Saving a task in the web interface when no calendar
holds tasks also creates Tasks. Bongo creates it outside the limit on calendars
per user, so an account already at the limit goes one over. An account that
already has a calendar holding tasks gets none. Tasks cannot be deleted.

## Creating and deleting calendars

`MKCALENDAR`, and extended `MKCOL` (RFC 5689) with a resource type of
collection plus calendar, both create the calendar at the requested path
`/caldav/{user}/calendars/{segment}/` and answer `201` with a `Location`
header.

- The `supported-calendar-component-set` is honoured. Without one the
  calendar holds events. `VEVENT` and `VTODO` together make a calendar that
  holds both. Other components are dropped. A set with neither answers `403`
  with the `supported-calendar-component` precondition.
- The display name becomes the calendar's name: control characters are
  removed and it is cut to 255 characters. Without one the segment is the
  name. Apple Reminders sends the placeholder `DEFAULT_TASK_CALENDAR_NAME` for
  its default list; Bongo stores that name as "Tasks". The description is kept,
  up to 4096 characters. Bongo ignores the
  colour, the order and the time zone the client sends, so the client's
  colour is not kept.
- A segment uses letters, digits, `_`, `.` and `-`, is at most 128
  characters, starts with a letter or digit, and keeps its case. It cannot
  start with `shared-` or `sub-`, or end in `.ics`.
- An existing path answers `405` with the `DAV:resource-must-be-null`
  precondition; Bongo never overwrites a calendar. Another user's path, a
  `shared-` path and an invalid segment answer `403`, decided before the store
  is read. `MKCALENDAR` outside a calendar collection path answers `403`
  with `calendar-collection-location-ok`. A plain `MKCOL`, or an extended
  `MKCOL` that does not ask for a calendar, answers `403`. A body over 64 KiB
  or bad XML answers `400`.
- A user owns at most 5 calendars. Personal, Tasks, created calendars and
  subscribed calendars all count; calendars shared with the user do not.
  A sixth create answers `507` with a `DAV:error` body naming
  `DAV:quota-not-exceeded`. At the limit an existing path still answers
  `405`. The automatic Personal and Tasks calendars are exempt. The limit and
  the existence check are enforced per node, not across a cluster.

`DELETE` on `/caldav/{user}/calendars/{segment}/` answers `204` and removes
the calendar with its events and tasks, its shares and its published feed;
the feed's link then answers `404`. A failure part-way answers `500`, and a
large calendar may outlast the client's timeout while the delete continues on
the server. These cases change nothing:

| Case | Answer |
|------|--------|
| `tasks` or `default` | `403` |
| The user's last calendar that holds events and is not a subscription | `409` |
| A subscribed calendar (unsubscribe in the web interface) | `409` |
| Another user's path, or a `shared-` path | `403` |
| A calendar that does not exist | `404` |

Up to v0.15.0, `MKCALENDAR` answered `405` and extended `MKCOL` ignored the
component set and the path, and no release could delete a calendar over
CalDAV.

## Limits

- One request body is at most 10 MiB; a larger one is refused with `413`.
- A user owns at most 5 calendars; see Creating and deleting calendars.
- Events, tasks and contacts count towards the domain's quota, checked at
  every `PUT`.
- An event can invite at most 100 attendees. Only attendees the server would
  invite count: the organiser's own `ATTENDEE` line, attendees with
  `SCHEDULE-AGENT=CLIENT` or `NONE`, and any other address you send as do not,
  and an address listed twice counts once. Bongo's structured copy of an event
  holds up to 200 attendees in all, those exempt ones included; the stored
  iCalendar keeps the full list. When you are the organiser and scheduling
  applies (the event has attendees to message), a `PUT` that invites more than
  100 is refused with `403` and the `max-attendees-per-instance` precondition.
  The web edit form refuses the same case.

## Checking a connection

Replace the host, address and password with real values. Each command
prints the HTTP status.

| Step | Command | Expected |
|------|---------|----------|
| Discovery on the mail host | `curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" -X PROPFIND https://mail.example.com/.well-known/caldav` | `301 https://mail.example.com/caldav/` |
| Discovery on the email domain | the same command against `https://example.com/.well-known/caldav` | a redirect to the mail host |
| Sign in | `curl -s -o /dev/null -w "%{http_code}\n" -u alice@example.com:PASSWORD -X PROPFIND -H "Depth: 0" https://mail.example.com/caldav/` | `207` |
| DNS | `dig +short SRV _caldavs._tcp.example.com` | `0 1 443 mail.example.com.` |

What a failure means:

- `405` on a well-known path: the server or website redirects `GET` only.
  Upgrade Bongo, or fix the website's redirect, or enter the server path in
  the client.
- `404` on the email domain's well-known path: the website has no redirect.
  Add the redirect or the DNS records, or enter the mail host in the client.
- `401` at sign-in: wrong password, the local part used instead of the full
  address, a disabled account, or a resource account.
- `429`: too many failed attempts from this address. Wait and try again
  with the correct password.
- A certificate error: the client refuses the connection. The mail host
  needs a valid certificate for its name.
{% endraw %}
