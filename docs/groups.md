---
layout: doc
title: "Group addresses: delivery and limits"
nav_title: "Group addresses"
permalink: /docs/groups/
source: https://github.com/bongo-project/bongo/blob/main/docs/groups.md
---
{% raw %}
# Group addresses: delivery and limits

Mail sent to a distribution group's address is delivered to each member as an
ordinary local copy.

## How delivery works

- At `RCPT TO` (inbound MX and authenticated submission) and in web compose, the
  group address is replaced by one recipient per member who can receive mail.
  A member whose account is gone, disabled or a resource is skipped.
- Each member's copy goes through the normal pipeline on its own: the member's
  rules, antispam result and quota check apply. All copies share one stored
  message.
- A member over quota is skipped and logged. If every member is over quota the
  sender gets `552 5.2.2`.
- A group adds no second copy for a user who already gets the message: one
  addressed directly, or a member of another group in the same message. When the
  user is addressed directly, their copy is the one for that address, with its
  folder routing and delivery-notification settings. Addresses given directly are
  not merged with one another, so a message to bob@ and bob+lists@ still arrives
  twice, as it always has.
- The copy that members receive carries `X-Bongo-Group: <group id>`. A message
  that already carries the header for a group is not expanded for it again, which
  stops a member's forward back to the group from looping. The header is not in
  the copy sent to outside recipients or in the sender's Sent folder.
- A group address in `To` is not one of the member's own addresses, so the copy is
  not "to me" in the header views and does not get a vacation reply.
- Delivery reports: `NOTIFY=SUCCESS` and `DELAY` are not passed on to members, so
  one request does not produce a report per member. The original recipient in a
  report is the group address.
- Posting policy decides who may send to a group:

  | Policy | Who may post |
  |---|---|
  | `anyone` (default) | everyone, including mail from the internet |
  | `domain` | signed-in users whose primary address is in the group's domain |
  | `members` | members and owners |
  | `owners` | owners only |

  The decision is made on the signed-in account, never on the `From` header, a
  send-as address or the envelope sender, all of which can be forged. For
  `domain`, the account's primary address must be in the group's own domain:
  aliases, send-as addresses and alias domains do not count.
  Mail from the internet (port 25) is never signed in, so any policy other than
  `anyone` refuses it at `RCPT` with `550 5.7.1 Posting to this group is
  restricted`. This tells an outsider that the address is a restricted group.
  Authenticated submission gets the same answer. Web compose refuses the whole
  send with an error naming the group, and sends to no one, including the other
  recipients, the same as for a group that is gone. A forwarding rule, or mail
  relayed through the outbound queue to a restricted group, returns over port 25
  unsigned, so it is refused and bounces. Mail the server generates for an
  account (calendar invitations, iMIP replies and share invitations) is expanded
  in process and checked against the posting policy as the triggering account, so
  it reaches a restricted group only when that account may post there; a refused
  group is listed among the recipients the message did not reach and nothing
  bounces.

## Fan-out limit

`smtp.limits.group_fanout_per_hour` (default 5000, `0` = off) caps how many member
copies one sender can cause per rolling hour. It is separate from
`outbound_recipients_per_hour`, which counts external recipients only.

| Mail | Counted per |
|---|---|
| Authenticated submission, web compose | the account |
| Inbound from the internet | the source IP |

The source IP is used for inbound mail because the envelope sender is free to
forge. Behind a trusted relay, or a TCP proxy without PROXY protocol, every
sender shares the relay's address and so one allowance.

The check is made at `RCPT` and the count is charged at `DATA`. A group that would
go over the limit is refused whole with `452 4.5.3 Too many group recipients, try
again later`; web compose shows an error. Keep the value at or above 1000, the
largest group, or a full group can never be posted to (the server logs a warning
at startup). The count is in memory and per node: a restart resets it, and with N
nodes the effective limit is N times the value. The setting is read at startup.

## Upgrades

Group delivery adds no stored data and no Raft command. A node on an older
binary answers `550` for a group address, so mail to a group bounces if it reaches
such a node. Upgrade every node before creating a group, and before setting a
posting policy other than `anyone`: an earlier binary does not enforce it.

Sharing with a group writes a grant naming the group, and deleting a group
removes its grants in the same step. A node on an older binary refuses or
misstores such a grant and keeps the grants of a deleted group, so upgrade every
node before anyone shares with a group.

## Managing groups

Global administrators and domain administrators manage groups under
**Admin > Groups** (`/admin/groups`). A domain administrator sees and edits only
the groups of the domains they administer. A group has an address, a display
name, members, owners and a posting policy. Members and owners must be existing
users (not rooms or equipment) whose address is on the group's own domain, and
the address of a group cannot be changed once created. An address already used by
an account, alias or group is refused.

Groups of your own domain appear in the address autocomplete when you write a
message, with their display name. Users of other domains do not see them.

## Sharing with a group

A calendar can be shared with a group of the owner's own domain by entering the
group address in the sharing form. Every member then has the permission given.
Unlike a share with a person, a share with a group is active at once: there is no
invitation to accept, because the group, kept by the administrators, is what the
owner trusts. Members see the calendar under **Shared with you** as "via" the
group and cannot leave it themselves; the owner removes the group from the
sharing list. When a member holds a permission of their own as well, the stronger
of the two applies. Taking someone out of the group ends their access straight
away, and deleting a group removes every share made with it.

## Groups as shared inbox members

A group can be a member of a shared inbox (see "Shared inboxes" in
`shared-folders.md`). Every member of the group then reads the inbox's folders
and may send from its address, and the same holds for anyone added to the group
later. Taking someone out of the group ends both on their next request. Deleting
a group removes the folder access it gave, in the same step. The group must be on
the shared inbox's own domain. A shared inbox itself cannot be a member of a
group: only people can.
{% endraw %}
