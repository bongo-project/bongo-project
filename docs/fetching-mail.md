---
layout: doc
title: "Fetching mail from other accounts"
nav_title: "Fetching mail"
permalink: /docs/fetching-mail/
source: https://github.com/bongo-project/bongo/blob/main/docs/fetching-mail.md
---
{% raw %}
# Fetching mail from other accounts

Bongo can collect mail from a POP3 or IMAP account somewhere else and deliver
it to your inbox, on a schedule. Open Settings, then "Fetch mail"
(`/settings/fetch`).

## Adding an account

Enter the protocol (IMAP or POP3), the connection security, the server name, the
user name and the password.

- **TLS only.** The connection is always encrypted and the server's certificate
  is always checked. There is no plain-text option and no way to skip the
  check. Choose "TLS (implicit)" for the usual secure ports, or "STARTTLS" where
  the provider asks for it.
- **The port is not typed.** It follows from the protocol and the security:
  IMAP 993 or 143, POP3 995 or 110. The page shows it.
- **Gmail and Outlook need an app password.** Bongo signs in with a user name
  and password only; it does not speak OAuth. For those providers, create an app
  password in the provider's account security settings and enter that. The
  provider's normal password will be refused.
- **Test connection** signs in and opens the folder, and fetches nothing. For a
  saved account the test always uses the stored server and password, whatever
  the form holds. Tests and resumes share a limit of 10 per hour per person (account creation and
  some saves count against it too; see below).
- The password is stored encrypted, is never shown again and is never sent back
  to your browser. When you edit an account, leave the password blank to keep
  it, unless you change the server, protocol, security or user name: then Bongo
  asks for the password again, so that nobody can point your account at another
  server without knowing it.

You can add up to 5 accounts. Adding an account, setting a new password,
changing the server, protocol, security or user name, and saving an account to
clear a pause each count against a limit of 10 per hour (shared with the
connection test and Resume), because each lets Bongo try the password again.
Editing only the label, interval, folder or leave-on-server setting is not
limited. Because the limit is checked just before the account is written, two
requests at the same moment can leave you with more than 5 accounts. If that
happens, delete accounts until you are back at 5.

## What is fetched, and when

Each account is checked every 15 minutes at the soonest; you choose 15 minutes,
30 minutes, 1, 3, 6, 12 or 24 hours. A check takes at most 500 messages or 256
MiB (by the sizes the server lists) and carries on at the next check, which
comes five minutes later when mail was left behind. Messages larger than the
server's SMTP size limit are not fetched. They are marked as handled and stay
on the other server, and the page counts them ("too large"). A check records
at most 50 such messages and carries on at the next one.

An account remembers up to 50,000 handled messages. Past that it stops
importing and the page says so ("too many handled messages"). In particular, a
leave-on-server account on a mailbox of more than 50,000 messages stops at this
limit. Only deleting or moving mail on the other server makes the list shrink
(Bongo forgets a message once it is gone from the folder). Turning "Leave
messages on the server" off before the limit is reached keeps the list small,
but it does not clear what is already recorded.

Fetched mail goes through the same checks as mail from the outside: your
filter rules, spam scoring, DKIM and the rest. It arrives with no sender
address for replies, so vacation replies and bounces are never sent for it.

- **Leave messages on the server** is on by default. Bongo remembers which
  messages it has handled and does not fetch them twice.
- When it is off, each message is deleted from the other account after Bongo
  has delivered it. With IMAP this needs the server to support UIDPLUS; without
  it the delivered messages are only flagged as deleted and nothing is
  removed. With POP3, deletions take effect when the session ends.
- **IMAP folder.** The default is INBOX. If you change the folder, every message
  in the new folder counts as new, because "handled" is remembered per folder.
- A message is delivered at least once. If Bongo stops at the wrong moment, one
  message can arrive twice; none is lost.
- **Mail that fails DMARC with `p=reject`** goes to your Junk folder, not to the
  administrator's quarantine. Bongo cannot check SPF for fetched mail (it did
  not arrive from the sender), so a sender that publishes `p=reject` and signs
  nothing would otherwise look forged; the other provider has already judged the
  message on arrival.
- A message that was delivered here but could not be deleted on the other
  server (the connection dropped, or the server refused) is marked as handled
  and is not tried again, so it stays there until you delete it yourself.
- **Quota.** A message that does not fit in your mailbox is not delivered and is
  not deleted from the other account. The page shows "mailbox is full".

Every fetched message carries an `X-Bongo-Fetched` header. Bongo uses it to
recognise its own mail when you forward from the other account back to
yourself, and skips such a message instead of storing it again. The value is
visible in the stored message. Anyone who learns it can make that one account
skip a message carrying it: the message then stays on the other server and is
never imported. This is accepted.

## When something is wrong

The page shows the last result for each account: when it last worked, when it
will next run, how many messages arrived, and the last error.

- After **five failed sign-ins in a row** the account is paused. Check the
  password (or app password) at the provider, edit the account if needed, then
  choose "Resume". Saving the account also resumes it.
- **"The stored password can no longer be read"** (needs password) means the
  server's credentials key changed or was lost. Edit the account and enter the
  password again.
- Other failures (the server is unreachable, a certificate problem, a missing
  folder, a POP3 server without UIDL) are retried with a growing delay of up to
  a day and are named on the page.

Deleting an account removes the stored password at once. Mail already delivered
stays in your mailbox, and nothing is deleted on the other server by the
deletion.

## For operators

Fetching is off until a credentials key is set. Without it, users see the page
read-only: they can list and delete accounts, and every other action is refused.

- Generate the key with `openssl rand -base64 32` and put it in
  `fetch.credentials_key` or in `BONGO_FETCH_CREDENTIALS_KEY`. It must be
  different from `web.session_secret`. See `deploy/bongo.example.hcl`.
- **Keep the key out of the data directory.** Startup is refused when a config
  file that holds the keys is inside `storage.data_dir`, because backups copy
  that directory. The key is never written to the database. A backup without
  the key cannot be used to read the stored passwords.
- **Every node of a cluster needs the same keys.** A node with no key serves
  the page read-only and does not fetch (its worker does not start). Only a
  leader that holds a different key, one that cannot open a stored password,
  marks those accounts "needs password".
- **Rotation.** Put the new key in `credentials_key`, move the old one to
  `previous_credentials_keys` and restart every node. Passwords are
  re-encrypted under the new key as each account is next fetched successfully.
  Remove the old key only after every account has had a successful run since
  the restart (the re-encryption happens on a successful run; the leader logs
  how many accounts are still under an older key). The startup log line
  `fetch: credentials key loaded` carries a `key_id` (derived from the key, not
  secret) so you can see which key a node holds.
- **Losing the key** means users must enter their remote passwords again.
- `fetch.allow_private_networks` lets Bongo connect to servers on your own
  network. By default connections to loopback, private and link-local
  addresses are refused, and only ports 993, 995, 143 and 110 are dialled.
- Only the leader node fetches. Page writes (saving, resuming) work when the
  request reaches the leader, as every other web write does.
- The log component is `fetch`. Logs carry the user id, the account id, the
  server name and a fixed error code; never the user name or the password.
{% endraw %}
