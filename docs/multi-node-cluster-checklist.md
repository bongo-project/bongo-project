---
layout: doc
title: "Multi-node cluster pre-flight checklist"
nav_title: "Multi-node cluster checklist"
permalink: /docs/multi-node-cluster-checklist/
source: https://github.com/bongo-project/bongo/blob/main/docs/multi-node-cluster-checklist.md
---
{% raw %}
# Multi-node cluster pre-flight checklist

Status: multi-node clusters are in planning. The base is in the product: Raft
consensus for all writes, gossip membership, blob sync between nodes, mutual
TLS for the Raft transport, gossip encryption, and the startup check described
below. Bongo is deployed and tested as a single node. This checklist records
what a cluster requires before it is formed.

The shipped deployment is a **single node**: one `server`-role process that only
ever talks to itself (`advertise_addr = 127.0.0.1`, no peers). In that mode raft
and gossip bind to loopback only, whatever `bind_addr` says, so they are not
reachable from other hosts or containers. Leaving the ports unpublished is not
what protects them: other containers on a shared compose network can reach
unpublished ports. The transport-hardening findings in
`security-review-2026-07-06.md` (H3/H4/M8) are therefore not exploitable on a
single node and were deferred; L6 is addressed for single node.

The moment you add a peer, that changes. bongo enforces this: a `server` with a
non-empty `cluster.join` **refuses to start** until gossip encryption and raft
mTLS are configured (`internal/config` `Config.Validate`). This checklist is
what that gate is guarding — work through it before forming a cluster.

## Why (the deferred findings)

- **H3 — gossip encryption.** Without `cluster.gossip.encryption_key`, gossip is
  plaintext and unauthenticated. Any host reaching the gossip port can join and
  broadcast forged node metadata (attacker-controlled `HTTPAddr`), poisoning the
  peer list the blob syncer trusts.
- **H4 — raft peer transport.** The raft TCP transport must not fall back to
  plaintext, and the dialer must actually verify peer certificates. Shipped: a
  node with peers fails to start if `cluster.tls` cert, key or CA is missing or
  unreadable (the error names the file), never opens a plaintext raft listener,
  requires and verifies a client certificate against the cluster CA, and the
  dialer never sets `InsecureSkipVerify`. A plaintext/unverified raft port
  lets an attacker drive consensus and overwrite the FSM.
- **M8 — blob-sync / join over HTTP.** Blob pulls and raft auto-join went over
  cleartext HTTP; on a real network that exposes user mail in transit. Shipped
  for a node with peers: see "Peer listener design note" below.
- **L6 — cluster bind address.** Raft and gossip no longer follow
  `server.bind_addr` (the protocol listeners' wildcard). They bind
  `cluster.bind_addr` when set, otherwise the advertise address: loopback for a
  single node, the node's private IP for a cluster member. A join with a
  loopback advertise address is refused at startup, and a hostname or wildcard
  that cannot be turned into an interface IP is refused rather than binding
  every interface.

## Checklist

1. **Generate a gossip encryption key** (16, 24, or 32 bytes, base64):
   ```
   openssl rand -base64 32
   ```
   Set the same value on every node:
   ```hcl
   cluster { gossip { encryption_key = "<base64-key>" } }
   ```
   There is no environment-variable override for this key (only
   `web.session_secret` has one, `BONGO_WEB_SESSION_SECRET`), and the HCL
   loader does not support `env()`. The key therefore lives in the config
   file: keep that file out of version control and readable only by the
   service user.

2. **Provision raft mTLS.** Give every node a certificate/key signed by a shared
   cluster CA, and point all three at that trust anchor:
   ```hcl
   cluster {
     tls {
       cert_file = "/certs/node.crt"
       key_file  = "/certs/node.key"
       ca_file   = "/certs/cluster-ca.crt"   # required for peer verification
     }
   }
   ```
   `ca_file` is mandatory once the node has peers (`cluster.join` set, a
   non-loopback `advertise_addr` or a non-loopback `cluster.bind_addr`); without it the node refuses to start.
   The dialer verifies the server name against the IP it dials, so each node's
   certificate must carry an **IP SAN** for that node's advertise address. The
   old `InsecureSkipVerify` hid this requirement: a certificate without IP SANs
   that formed a cluster before will now fail the handshake.

3. **Bind cluster transports privately.** Set `server.advertise_addr` to the
   node's private IP (an IP literal, not a hostname, not `0.0.0.0`, not
   loopback). Raft and gossip listen on that address by default; `server.bind_addr`
   does not affect them. If the advertise address is not on a local interface
   (NAT, Docker bridge), set `cluster.bind_addr` to the local interface IP
   instead, otherwise the bind fails with "cannot assign requested address".
   Ensure the raft (8300), gossip (8301) and peer (8302) ports are reachable **only**
   between nodes, never published to the internet or through Traefik.

4. **Verify the code-level hardening is in place** before rollout (these are the
   deferred fixes; confirm they were implemented, not just configured):
   - raft refuses to start clustered without mTLS instead of falling back to
     plaintext; peer certs are verified against `ca_file` (shipped).
   - blob-sync and raft join use `https://` over the mutually authenticated peer
     listener (`cluster.peer_port`, default 8302; shipped, see the design note).
   - agent gRPC (`internal/agent/grpc`) is mutual TLS in both directions from
     `agent_server.tls.{cert_file,key_file,ca_file}` (shipped). A missing or
     unreadable file refuses start and names the key; there is no plaintext
     fallback. Its logger goes through slog (15.4).
     - Clients verify the server against `ca_file`, using the host in
       `agent_server.address` as the name, so that certificate needs a matching
       IP or DNS SAN. The same applies to the address an agent registers.
     - One cert/key pair is used both as server certificate and as client
       certificate, so it needs both `serverAuth` and `clientAuth` extended key
       usage. A `serverAuth`-only certificate is rejected.
     - The listeners bind the cluster bind host (`cluster.bind_addr`, else
       `server.advertise_addr`, else `server.bind_addr`; a wildcard is
       refused), not every interface. An `agent` node with processor roles
       (antispam, antivirus) therefore needs `cluster.bind_addr` or
       `server.advertise_addr` set to its own interface IP.
     - Role `server` and `dev` do not run the agent gRPC server yet, so nothing
       in a server-role node dials or listens for agents and
       `DispatchOrLocal` is not live. Agent mode cannot register with a
       server until that is wired in.

5. **Form the quorum with 3 or 5 nodes.** Never run 2 or 4 (no fault tolerance /
   split-brain risk). Only the first node bootstraps; the rest set `cluster.join`.

6. **Stagger the daily cold backup** so only one node cycles at a time and the
   raft quorum + leader stay up throughout. The backup procedure itself is in
   section 10 ("Backup") of `deploy/README.md`.
   Do not plan on `edge` or `agent` nodes to absorb inbound mail while a server
   node is down: both roles are incomplete. An `edge` node starts no SMTP,
   IMAP or POP3 listeners, because those require Raft, which only the `server`
   and `dev` roles start. An `agent` node registers with a server over gRPC,
   but no server constructs the gRPC `AgentServer` it registers with (see
   step 4).

7. **Run one binary version on every node** before using any feature listed
   under [Mixed-version clusters](#mixed-version-clusters).

## Mixed-version clusters

Run one binary version on every node before using any feature listed here.
Nodes do not publish their version, and a new command type is not gated on the
cluster's lowest version. Version gating is outstanding work (see
`prds/done/prd-hardening-v0.9.md`, 8.2).

### What an older node does

Every write goes through the Raft log, and each node applies it with
`FSM.applyProto` (`internal/cluster/fsm.go`). A composite command is a `PUT` to
a synthetic key prefix such as `/__acl__/`, which the FSM sends to an
`Is*SyntheticCommand` predicate. Two things can happen on a node whose binary
does not match:

- **The prefix is unknown to it.** No predicate matches, so the command falls
  through to the plain `f.store.Set(cmd.Key, cmd.Value)` and is stored as a
  literal Pebble key. None of the intended keys is written.
- **The prefix is known but the payload is not.** The command fails validation,
  the FSM logs an error (for example `fsm: acl synthetic command failed`) and
  writes nothing.

In both cases the node still records the entry as applied
(`setAppliedIndex`, `/system/raft/applied_index`). Replaying the log after the
node is upgraded skips that entry, so **upgrading afterwards does not repair
the node**. Its replicas stay diverged until its data is rebuilt, not only for
the length of the mixed window.

"Older node" here means any v0.15.x binary (the latest release is v0.15.15).
The rule is the same for all of them: upgrade every node first. Production
runs one node, so this applies only to a cluster.

### Commands that need every node upgraded

New or extended in v0.16 (checked against v0.15.15):

| Command | What an older node does | What breaks |
|---|---|---|
| `/__group__/` (`internal/store/groupcommand.go`), new | Stores a literal key. | No group, no group address record and no member index on that node. A group address is never resolved there. Whether mail to it bounces depends on the domain: with a catch-all the resolver hands it to the catch-all owner, otherwise the RCPT is refused with 550 5.7.1 or 5.1.1 (`internal/smtp/server.go`, hosted-domain check). Posting policies other than `anyone` are not enforced there. User deletion sends `remove_user` every time, so the older node gains a harmless literal key on each deletion. |
| `/__mailbox_assignid__/` (`internal/store/mailbox.go`), new | Stores a literal key. `IsMailboxSyntheticCommand` in v0.15.15 lists only append, copy, delete, deliver, expunge, move, rename and subscribe. | The node holds no mailbox id. Its rename drops the id and leaves the `mailboxid` lookup key stale, and its delete leaves that key behind. `MailboxNameByID` reads these cases as not found. |
| `/__mailbox_xfer__/` (`internal/store/mailbox_transfer.go`), new | Stores a literal key. | The destination copy of a cross-owner COPY or MOVE is missing on that node. For a MOVE the source message is still there too. |
| `/__user_usage__/` (`internal/store/user_usage.go`), new | Stores a literal key. | The node holds no per-user usage, reads 0 and does not enforce `UserProfile.quota_bytes`. Enforcement depends on which node takes the request. |
| `/__acl__/` with kind `mailbox` or `addressbook` (`internal/store/aclcommand.go`), extended | Refuses it at validation: v0.15.15 knows only `calendar` (`aclKinds`). Nothing is written. | Folder and address-book grants are missing on that node. Its owner revoke and orphan sweep ignore these kinds. It lists no shared address books and answers 404 on CardDAV `shared-` paths, so a client balanced across nodes sees the book appear and vanish. |
| `/__acl__/` with a `g:` grantee, extended | v0.15.15 `ACLKey` always writes `/u:` plus the grantee, so a group grant lands under a bogus user grantee that authorises nobody. | The group's members get no access on that node. It also has no `/__group__/`, so deleting a group there leaves the grants behind. |

Already required a full upgrade in v0.15:

- `/__acl__/` itself, including the `accept` op and `keep_state` (calendar
  sharing and the invitation flow).
- `/__bayes_train__/{user}`: an older node counts nothing, so Bayes counts
  diverge and cannot be recovered by replay.
- `/__apppassword_touch__/`: an older node stores a literal key and
  `last_used_at` lags. Authentication is unaffected.
- `/__apppassword_ticket__/consume`: an older node leaves the device link
  unused, so a link can be redeemed on more than one node.

### Shared inboxes

A shared inbox is not a command. `UserProfile.kind = "shared"` and field 16
`shared_members` are plain profile writes, and an older node keeps both. The
risk is in what the older node does not check. In v0.15.15,
`auth.CheckStanding` refuses only a disabled account or kind `resource`
(`internal/auth/local.go`), and the admin `ResetPassword` handler refuses only
resources (`internal/web/handlers/admin.go`). An admin using an older node can
therefore set a password on a shared account, and that account could then log
in there over web, IMAP, POP3, SMTP and DAV. Send-as for a shared address fails
closed on an older node. Upgrade every node before creating a shared inbox.

### Before you upgrade

Upgrade every node, then start creating groups, sharing folders, address books
or calendars, using cross-owner copy or move, setting per-user quotas or
creating shared inboxes. Nothing in the server stops you doing these earlier.

## Peer listener design note (blob sync and cluster join)

Before this change, both peer-facing endpoints were routes on the public web
router, served by `Agent.httpServer`:

- `POST /internal/cluster/join` sits behind `middleware.RequireInternalAuth`
  (HMAC with the effective session secret, `security.SignInternalRequest`).
- `GET`/`HEAD /internal/blob/{hash}` sit behind `middleware.RequireBlobSyncAuth`
  (HMAC with a separately derived key, `security.SignBlobSyncRequest`). They are
  not behind `RequireInternalAuth`, and must keep their own check.
- The listener is `server.bind_addr:web.port` (normally `0.0.0.0:443`), TLS when
  `web.tls` is set. Peers authenticated by HMAC only: no transport protection
  beyond whatever the web listener has, and the public web port carried peer
  traffic.
- Gossip advertised that same address as `NodeMeta.HTTPAddr`, so peers were
  handed `0.0.0.0:443`, which from another host dials itself. Blob pulls and
  auto-join could not reach a peer in a real multi-node cluster, and both used
  `http://` regardless.

Design (smallest that satisfies the guardrail of a private listener plus
explicit auth):

- When `Config.ClusterHasPeers()` is true (the same definition raft uses, no
  second one), the node opens a **peer listener** on
  `ClusterBindHost():cluster.peer_port` (default 8302). It uses the strict
  cluster mTLS config (`cluster.LoadPeerTLS`, which is the raft loader):
  cert, key and CA are mandatory and a missing file fails startup naming the
  file, before any listener opens. `RequireAndVerifyClientCert` against the
  cluster CA, TLS 1.2 minimum, explicit server timeouts.
- The peer listener serves only `POST /internal/cluster/join` (still behind
  `RequireInternalAuth`) and `GET`/`HEAD /internal/blob/{hash}` (still behind
  `RequireBlobSyncAuth`). The HMAC checks stay as a second factor.
- On a node with peers those three routes are **not** registered on the public
  router, so the web port answers 404. Without peers nothing changes: the routes
  stay on the public router, no listener opens, no new config is required.
- Gossip metadata gains `peer_addr` (`MemberInfo.PeerAddr`), the advertise
  address plus peer port (`Config.ClusterPeerAddr`). `HTTPAddr` is unchanged
  (the admin cluster page shows it). The advertise address is used, not the bind
  host, so NAT setups work.
- Clients: when the node has peers, `BlobSyncer` (HEAD and GET) and the
  auto-join POST use `https://<PeerAddr>` with an `http.Client` whose
  `tls.Config` has the cluster CA as `RootCAs` and the node certificate for
  client auth. A peer without `PeerAddr` (older node) is skipped and logged,
  never contacted over `http://`. A peer certificate from another CA fails the
  call, and the failure is logged at warn with the peer name (never the secret
  or blob content). Pulled blobs are still re-hashed and rejected on mismatch.
- The node certificate must carry an IP SAN for the advertise address, because
  the client verifies the dialled IP. Firewall 8302 between nodes like 8300 and
  8301.
- Mixed versions: an older node advertises no `peer_addr`, so a TLS node will
  not sync from it. Multi-node clustering has not worked end to end before this
  (the advertised address above), so no live deployment depends on it.
- Single node with loopback advertise, and dev, are unchanged: a mail
  certificate in `cluster.tls` with no `ca_file` is still accepted and the
  strict loader is never called for the peer listener.

Every other `/internal/*` route (queue, user create, address repair,
snapshot, dangling mail, cluster members, and in dev `/internal/kv/*`) is
served only on the loopback control listener (`server.control_addr`, default
`127.0.0.1:8081`), still behind HMAC. The web port answers 404 for them.

## Sanity check

With `cluster.join` set but the gossip key or any `cluster.tls` file missing,
startup fails with (the `set` clause names only what is missing):

```
invalid config: cluster: joining peers requires transport security before a multi-node cluster can form; set cluster.gossip.encryption_key and cluster.tls.{cert_file,key_file,ca_file} (see docs/multi-node-cluster-checklist.md)
```

With `cluster.join` set and the advertise address (`server.advertise_addr`,
or `server.bind_addr` when that is unset) a loopback address, it fails with:

```
invalid config: cluster: cluster.join is set but raft/gossip advertise the loopback address "127.0.0.1"; set server.advertise_addr to this node's routable IP
```

Single-node deployments (empty `cluster.join`) are unaffected and start exactly
as before.
{% endraw %}
