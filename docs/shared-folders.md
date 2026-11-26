---
layout: doc
title: "Sharing folders from a mail client"
nav_title: "Sharing folders"
permalink: /docs/shared-folders/
source: https://github.com/bongo-project/bongo/blob/main/docs/shared-folders.md
---
{% raw %}
# Sharing folders from a mail client

Bongo shares a mail folder the way it shares a calendar: the owner grants a
person or a group some rights, and the grantee accepts. Folders can be shared
from the web interface or from any IMAP client that speaks the ACL extension
(RFC 4314). Both write the same grants.

Shared folders appear to the grantee under the "other users" prefix
(`Other Users/{owner address}/{folder}` by default, see `imap.other_users_prefix`).

Before anyone shares a folder, upgrade every node of a cluster. A node on an
older binary cannot apply folder grants, so its replicas would diverge.

## Commands

The server advertises `ACL`. The commands are those of RFC 4314:

- `MYRIGHTS` reports what you may do in a folder you can see. The owner holds
  all of `lrswipkxtea`.
- `GETACL` lists the owner and every accepted or pending grant, naming a person
  by their primary address and a group by its address. Grants whose invitation
  has expired are not listed. It needs the `a` right.
- `LISTRIGHTS` says which rights may be granted: the owner's are fixed, and
  anyone else may be given any single letter of `lrswipkxtea`. It needs `a`.
- `SETACL` grants, adds (`+`) or removes (`-`) rights. It needs `a`.
- `DELETEACL` removes one grant. It needs `a`.

A folder you cannot see, including one with a pending invitation or without the
lookup (`l`) right, answers exactly like a folder that does not exist.

## Who can be named

- A local user, by any address that reaches their account.
- A group, only when it is on the owner's domain.

Anything else, whether an external address, an unknown one, a disabled account,
a group of another domain, `anyone`, `authenticated` or a negative identifier
(starting with `-`), is refused with the same text. The answer never says
whether the address exists elsewhere. Sharing is limited per person and hour,
shared with the web share form, so it cannot be used to look up accounts.

The owner's own rights cannot be changed or removed by anyone.

## What a grant does

- A new person gets a pending grant and the same invitation mail the web sends.
  The folder shows in their list once they accept it on the shares page.
- Changing the rights of someone who already holds a grant keeps its state and
  sends no mail.
- A group on the owner's domain is added accepted, with no mail.
- A folder can have at most 50 grants. When it is full, `SETACL` for anyone not
  already on it answers `NO [LIMIT]`, whether or not the address is real.
- Removing every right (`SETACL ... ""`, `-` of everything, or `DELETEACL`)
  revokes the grant.
- Unknown rights (`c` and `d` from RFC 2086 included) are refused with `BAD`.
  Rights are stored in the order `lrswipkxtea`, whatever order the client used.

A person who holds `a` on a folder may grant any right, `a` included, and may
change or remove other people's grants. The grant records who made it.

## In the web interface

### Sharing a folder

Open Settings, Folders. Each of your folders has a form: the address of a
person or a group, an access level and, for Full only, "Can share". The levels
are presets:

| Level | Rights | Lets the person |
|-------|--------|-----------------|
| Read | `lrs` | look up the folder, read messages and mark them read |
| Write | `lrswite` | also change flags, add messages, delete messages and expunge |
| Full | `lrswipkxte` | also post and create or delete sub-folders |
| Full, can share | `lrswipkxtea` | also share the folder with others (over IMAP `SETACL`) |

The same rules as for IMAP apply: a person gets a pending grant and an
invitation mail, a group on your domain is accepted straight away, every
refusal reads the same, and sharing is limited per person and hour, one budget
for the web calendar form, this form and IMAP. The page lists who has access,
whether each grant is pending, accepted or expired, and lets you revoke it. A
set of rights an IMAP client chose that matches no preset shows as "Custom".

### Using a shared folder

An accepted folder appears in the sidebar under "Shared with me", grouped by
owner, with an unread count where you hold the read right. Invitations wait on
the shares page. Shared folders are not part of All Mail, Unread, Starred or
the header views.

The web interface offers on a shared message only what your rights allow:

- read, download attachments and export (`r`);
- mark read or unread (`s`);
- star (`w`);
- delete permanently (`t` and `e`).

Reply, forward, move, copy, archive, spam marking, tags and bulk selection are
not offered on a shared folder yet; use an IMAP client for those.

Things to know:

- Read, starred and answered are the owner's flags. When you read a message you
  mark it read for the owner too, and the owner's unread count falls.
- Delete is permanent. There is no move to Trash, because that would need the
  right to insert into the owner's Trash. Deleting expunges the folder, which
  also removes any message in it that an IMAP client has already marked as
  deleted, exactly as IMAP `EXPUNGE` would.
- Every request is checked against your current rights. Revoking a grant,
  leaving a group, renaming or deleting the folder takes effect on the next
  click, and a folder you cannot see answers like one that does not exist.
- Sharing from the web creates the folder's id, the grant and the invitation as
  separate steps, as `SETACL` does. A failure part way leaves at most an
  unused id or a grant without a mail.

## Shared inboxes

A shared inbox is an account such as `support@example.com` that nobody signs in
to. An administrator creates it under **Admin > Users > Create shared inbox**,
with a name and optionally its first members, and manages the members on the
account's page. A member is a user or a group of the shared inbox's own domain
(for every administrator, global ones included), at most 50 in all. Use a group
when many people need access.

Members get:

- **The folders.** Every folder of the shared inbox is shared with each member
  with the Write preset (`lrswite`: read, flags, insert, delete and expunge, no
  folder creation), accepted at once with no invitation. It appears in a mail
  client under `Other Users/support@example.com/…`, exactly like a folder shared
  by a person, and under "Shared with me" in the web interface.
- **The address.** The member can choose `support@example.com` as From in the web
  composer (it appears in the From list) and over SMTP submission. Folder rights
  alone never allow sending; only the member list does. People who are not
  members get a refusal on both.
- **Sent copies.** A message sent from the web as the shared address is filed in
  the member's own Sent folder and, when the shared inbox has a Sent folder, in
  the shared inbox's Sent folder too (a full shared inbox or a missing Sent folder
  only skips that second copy; the message is still sent). Over SMTP the server
  files no copy: set the mail client to save sent mail in `Other Users/
  support@example.com/Sent` if the team should see it.

Removing a member (or taking them out of a member group) ends the folder access
and the right to send on their next request. Nothing is cached. The folder grants
are revoked one by one; if that fails the page says so and the same removal can be
repeated, and a background sweep removes a leftover grant of anyone no longer on
the list.

The shared inbox has no password and cannot sign in on any protocol: the answer
is that of a wrong password. It has no app passwords. Administrators cannot set a
password for it. The shared inbox can be disabled or deleted like any account;
deleting it removes its mail and every grant on it.

Things to know:

- Setting up the mail client: add the shared inbox's folders through the
  `Other Users` namespace, and set the identity's From address to
  `support@example.com` (with the member's own login for SMTP submission).
- Vacation replies: a member's vacation responder does not answer for the shared address. Mail addressed only to `support@example.com` is not mail addressed to the member.
- Replying from the shared inbox in the web interface, and moving or copying
  messages out of a shared folder, are not offered yet.
- Upgrade every node before creating a shared inbox. A node on an earlier
  version does not refuse a password change on the account and would let it sign
  in there.
{% endraw %}
