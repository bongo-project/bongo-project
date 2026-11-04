---
layout: doc
title: "Config reload on SIGHUP"
nav_title: "Config reload"
permalink: /docs/config-reload/
source: https://github.com/bongo-project/bongo/blob/main/docs/config-reload.md
---
{% raw %}
# Config reload on SIGHUP

Status: increment 1 is implemented (`internal/agent/reload.go`,
`internal/config/diff.go`, and `watchSignals` in `cmd/bongo/agent.go`).
Increments 2 and 3 (section 9) are not built. This document began as the
design for backlog item B9 (task 16.7); the design rationale is kept, and
statements of fact have been corrected to match the code.

Citations: every `file:line` below is historical, pinned at `b2eb0b9`
(`norman/phase-15-logging`), and the code has moved since. Each citation also
names the enclosing symbol, for example
`internal/smtp/server.go:130 (Backend.SetTrustedNetworks)`. Re-find by symbol,
not by number.

## 1. Problem

A config-only change today costs `docker compose restart bongo`: about 12
seconds of downtime, and every live SMTP and IMAP session is dropped. The goal
is to apply the safe subset of changes in place on SIGHUP, and to say loudly
when a changed key still needs a restart.

A partial reload that silently ignores the restart-only keys would be worse
than no reload. The rule for this design is therefore: every changed key is
either applied or reported as "needs restart"; none is dropped silently.

## 2. How config is loaded today

`runServe` (`cmd/bongo/agent.go:53`) does the following, in order:

1. Builds a fresh `viper.New()` (`:77`) and calls `v.Set` only for flags the
   operator actually passed: `config` (`:79`), `role` (`:82`), `bind` (`:85`),
   `join` (`:88`), `log-level` (`:91`), and `skip-discovery` for `--dev` with no
   `--config` (`:98`).
2. Calls `config.LoadWithDiscovery(v)` (`:101`;
   `internal/config/config.go:1039`), which:
   - starts from `Defaults()` (`:1040`);
   - runs file discovery (`DiscoverConfigFile`, `:1048`): explicit `--config`,
     then `BONGO_CONFIG`, then `./bongo.hcl`, then `/etc/bongo/bongo.hcl`;
   - decodes the file with `hclsimple.DecodeFile` (`LoadFromFile`, `:1021`,
     hcl/v2 v2.24.0). Note `LoadFromFile` decodes ONTO `Defaults()`, so a key
     absent from the file keeps its default;
   - enables `AutomaticEnv` with prefix `BONGO` and `.` replaced by `_`
     (`:1063-1065`);
   - applies overrides from viper for `role` (`:1068`), `bind` (`:1071`),
     `join` (`:1074`), `log-level` (`:1078`) and `web.session_secret`
     (`:1083`, reachable as `BONGO_WEB_SESSION_SECRET`).
3. Applies `--plain-http` to `cfg.Web.PlainHTTP` AFTER loading (`:116-117`).
4. Validates. Startup now loads through `loadServeConfig`, which calls
   `config.LoadWithDiscovery` and then `cfg.Validate()`; an invalid config makes
   `bongo serve` refuse to start. (At `b2eb0b9` `Validate` was not called
   here; task 16.5 (B8) wired it.)
5. Builds the logger from `cfg.Telemetry.Log` once (`:121-142`) and hands `cfg`
   to `agent.NewAgent` (`:108`).

`NewAgent` then mutates the config it was given: in dev role it sets
`cfg.Web.PlainHTTP = true` (`internal/agent/agent.go:266`, `NewAgent`). So the
config the process is running on is not byte-identical to what the loader
returned.

Two facts about env handling matter for reload:

- The process environment cannot change after start, so applying the
  overrides again (`config.ApplyOverrides`) with the SAME viper instance
  reproduces the same env overrides. Under systemd, `EnvironmentFile=` (`deploy/bongo.service`) is
  read at service start only, so editing `/etc/bongo/bongo.env` still needs a
  restart. This must be stated in the operator docs.
- The `log-level` override key has no practical env form. With the replacer
  that maps only `.` to `_` (`config.go:1064`), the env name would be
  `BONGO_LOG-LEVEL`. In practice `--log-level` is the only way to shadow the
  file's level.

### Design consequence 1: reload must repeat the startup precedence

Re-parsing only the HCL file would silently revert `--log-level`, `--bind`,
`--role`, `--join`, `--plain-http`, and `BONGO_WEB_SESSION_SECRET`. The reloader
must therefore:

1. Keep the startup `*viper.Viper` (and the `servePlainHTTP` flag value) alive
   for the life of the process.
2. Pin the file: after the first load, `runServe` resolves the path to an
   absolute one and calls `v.Set("config", abs)`, so a reload re-reads the
   SAME file instead of re-running discovery (a newly created `./bongo.hcl`
   does not change which file is read on SIGHUP). If startup found no file,
   no reloader is enabled and a reload logs
   `config reload: no config file in use, nothing to reload` and returns.
3. Re-read the pinned file with `config.LoadFile` (which also returns the
   file's mtime and size), apply the flag and env overrides to a clone of it
   with `config.ApplyOverrides(v, merged)` (the same function startup uses, so
   the precedence cannot drift), then re-apply `--plain-http`. Discovery is
   not re-run.
4. Log every key whose flag or env value differs from the file value at WARN
   as `config reload: key shadowed by flag or env, file value ignored` (key
   name only). This fires on every reload for as long as the override and the
   file disagree, whether or not the file value changed since the last
   reload. Example: `--log-level=debug` was passed and the file says `info`:
   the file value does not take effect, and each reload warns about
   `telemetry.log.level`.

### Design consequence 2: the baseline for diffing is a snapshot, not `a.Config`

The reloader keeps its own deep copy of the config (taken after
`--plain-http` is applied and BEFORE `NewAgent` runs, so dev-mode mutation at
`agent.go:266` does not show up as a diff). It is stored in an
`atomic.Pointer[config.Config]` owned by the reloader and used only for
diffing. `Config` contains pointer members (`Queue`, `AgentServer`,
`Antispam.SpamAssassin`, `Antispam.DNSBL`) and slices, so the copy must be
deep, not a struct assignment.

## 3. Concurrency rule

NEVER mutate `*a.Config` in place. Treat it as an immutable startup snapshot.
Reasons, all verified in source:

- `Agent.Config` is a plain `*config.Config` field (`agent.go:92`) read in
  roughly 105 places in `internal/agent/agent.go` alone (`grep -c "a.Config"`
  returns 106 lines), from request handlers, goroutines and tickers, with no
  lock.
- `smtp.Relay` stores a pointer into it: `NewRelay(&a.Config.SMTP.Relay, ...)`
  (`agent.go:1239`) and reads `r.cfg.Enabled`, `Host`, `Username`, `Password`,
  `AllowInsecureAuth` on every delivery (`internal/smtp/relay.go:91,98,101,
  251-258`, `Relay.Deliver` and `sendToHost`).
- `agent.go:2597` reads `a.Config.Web.SessionSecret` per request when signing
  internal peer requests, and `agent.go:1559,1605` read
  `a.Config.Storage.BlobGCMode()` on every orphan-GC tick
  (`runOrphanGC`, `blobGCPass`). Both would be torn reads under in-place
  mutation.

Each hot key therefore gets its own race-safe path (section 5). A new config
snapshot is built beside the old one; only the dedicated holders change.

## 4. Classification of every config key

Method: every field of every struct reachable from `config.Config`
(`internal/config/config.go:15`) was read from the struct bodies, not grepped
from tags, then each was traced to its reader with
`grep -rn` over `internal/` and `cmd/`. Repeated blocks (`pipeline.stage`,
`antispam.dnsbl.zone`) are listed once with their attributes.

Legend for "How read today":

- `ctor` = value copied or acted on once while a component is constructed at
  startup.
- `ptr` = component holds a pointer into `a.Config` and reads it later.
- `tick` = read from `a.Config` on each tick of a loop.
- `none` = no reader exists in non-test code at `b2eb0b9` (see section 4.2).

Legend for "Class":

- HOT-1 = hot-reloadable, ships in the first increment.
- HOT-2 / HOT-3 = hot-reloadable in principle, deferred to a later increment
  (reason given).
- RESTART = restart-required. In increment 1 EVERY key not marked HOT-1 is
  reported as needs-restart, even where it is theoretically swappable.
- NO-OP = parsed but unread (changing it has no effect at all).

### 4.1 Table

`server`

| Key | Consumer (file:line, symbol) | How read today | Class |
|---|---|---|---|
| `server.role` | `agent.go:251,259,316,379,583,1143` (`NewAgent`, `Run`) and many others; `cluster/raft.go:58,76,173` | ctor, branches the whole startup path | RESTART |
| `server.name` | `cluster/raft.go:43` (raft LocalID), `cluster/gossip.go:34`, `agent.go:2569,2579,2585,2659,2805` | ctor; also per-call in peer-join code | RESTART (it is the raft node identity) |
| `server.datacenter` | none | none | NO-OP |
| `server.bind_addr` | `smtp/server.go` (listenAddr); `agent.go:942,1342,1343,1385,1386,1452,1453,2636,2796`; `cluster/raft.go:87`; `cluster/gossip.go:35` | ctor, listener addresses | RESTART |
| `server.advertise_addr` | `cluster/raft.go:89`, `cluster/gossip.go:58` | ctor | RESTART |
| `server.control_addr` | `agent.go` (`Run`, control listener bind) | listener address | RESTART |
| `server.agents` | `agent.go:2624,2643,2698` (`runAgent`) | ctor; agent role only | RESTART |
| `server.trusted_proxies` | `agent.go` `trustedProxies` (`ServerConfig.ParseTrustedProxies`) -> PROXY-protocol listeners and `middleware.SetTrustedProxies` | ctor, parsed once at startup | RESTART |

`agent_server` (pointer block; only meaningful for role `agent`)

| Key | Consumer | How read today | Class |
|---|---|---|---|
| `agent_server.address` | `agent.go:2625,2658,2804` (`runAgent`, `startProcessorAgent`) | ctor, gRPC dial target | RESTART |
| `agent_server.tls.cert_file`, `.key_file`, `.ca_file` | `agent.go` `startProcessorAgent` -> `agentgrpc.NewAgentProcessorServer`; `agentgrpc.AgentServer.Start` (server side, not yet wired) | ctor, read once at listener start (mutual TLS) | RESTART |

`cluster`

| Key | Consumer | How read today | Class |
|---|---|---|---|
| `cluster.bind_addr` | `cluster/raft.go`, `cluster/gossip.go` via `Config.ClusterBindHost` | ctor, transport listen address | RESTART |
| `cluster.join` | `agent.go:992-993` (gossip join); `cluster/raft.go:174`; `config.go:744` (Validate gate) | ctor | RESTART |
| `cluster.raft.data_dir` | none (raft snapshots use `Storage.DataDir`, `cluster/raft.go:135`; the log lives in Pebble) | none | NO-OP |
| `cluster.raft.port` | `cluster/raft.go:86` | ctor | RESTART |
| `cluster.raft.snapshot_threshold` | `cluster/raft.go:206-207` (`applyRaftTuning`) | ctor, copied into `raft.Config` | RESTART |
| `cluster.raft.snapshot_interval` | `cluster/raft.go:209` via `RaftSnapshotInterval()` | ctor | RESTART |
| `cluster.raft.trailing_logs` | `cluster/raft.go:210-211,219` | ctor | RESTART |
| `cluster.gossip.port` | `cluster/gossip.go:36` | ctor | RESTART |
| `cluster.peer_port` | `agent/agent.go` (peer listener) | startup | RESTART |
| `cluster.gossip.encryption_key` | `cluster/gossip.go:44` | ctor. SECRET | RESTART |
| `cluster.tls.cert_file`, `.key_file` | `cluster/raft.go:99,313`; ALSO IMAP and POP3 listener TLS: `agent.go:1314-1315,1364-1365` via `mailListenerTLS` (`:2882`) | ctor; loaded once | RESTART |
| `cluster.tls.ca_file` | `cluster/raft.go:323-324` | ctor | RESTART |

Note: IMAP and POP3 have no TLS block of their own; they reuse
`cluster.tls.*` (`agent.go:1314,1364`). A change there affects mail-client
TLS as well as raft transport.

`storage`

| Key | Consumer | How read today | Class |
|---|---|---|---|
| `storage.data_dir` | `agent.go:258,273` (Pebble dir), `cluster/raft.go:135` | ctor | RESTART |
| `storage.pebble.cache_size` | `NewAgent` -> `PebbleConfig.CacheBytes()` -> `pebbleStoreOptions` -> `store.WithCacheSize` (16.20) | ctor | RESTART |
| `storage.pebble.wal_dir` | none | none | NO-OP |
| `storage.attachment_dedup_min_size` | `agent.go:818` (`composeH.SetAttachmentDedup`), `agent.go:1085` (`deliverProc.SetAttachmentDedup`) | ctor, int copied into two handlers | RESTART (HOT-3 candidate: two setters, both plain fields) |
| `storage.min_free_mb` | `NewAgent` -> `diskspace.New` (sampled every 10 s); gates SMTP MAIL, IMAP APPEND, web compose/import, CalDAV/CardDAV PUT | ctor | RESTART |
| `storage.blob_gc` | `agent.go:1559` (log), `agent.go:1605` (`blobGCPass`) | tick: reads `a.Config.Storage.BlobGCMode()` every 15 min (`orphanGCInterval`, `agent.go:1530`) | RESTART in increment 1 (see 4.3) |

`smtp`

| Key | Consumer | How read today | Class |
|---|---|---|---|
| `smtp.enabled` | `agent.go:1142` | ctor, gates listener creation | RESTART |
| `smtp.port`, `smtp.submission_port` | `smtp/server.go:623-624` (`NewServer`); `agent.go:574` (autoconfig) | ctor | RESTART |
| `smtp.submissions_port` | `smtp/server.go` (`NewServer`); `agent.go` (autoconfig) | ctor | RESTART |
| `smtp.hostname` | `smtp/server.go:645` (banner and `Received`), `agent.go:571,588,697,1092,1235,1251,2416` (autoconfig, authserv-id, HELO, bounce domain) | ctor; copied into at least six components | RESTART |
| `smtp.proxy_protocol` | `smtp/server.go:706,734-735` | ctor, wraps listeners | RESTART |
| `smtp.srs_max_age_days` | `agent.go` `initSRS` | ctor: baked into the SRS codec in `Run` | RESTART |
| `smtp.postmaster_account` | `agent.go` `newRecipientResolver` | ctor: `RecipientResolver.SetPostmasterAccount` before the resolver is shared; also covers `abuse@` | RESTART |
| `smtp.srs_bounces_per_address_per_hour`, `smtp.srs_bounces_per_hour` | `agent.go` `buildPipelineStages` | ctor: `mail.NewRateLimiter` handed to `SetSRSBounceLimiters` | RESTART |
| `smtp.trusted_networks` | `agent.go:1169-1173` (server role) and `agent.go:2747-2751` (agent role, inert: gRPC `DepositMessage` strips `Trusted`, comment at `:2742`); `smtp/server.go:76,131,139,149` | ctor: parsed once, handed to `Backend.SetTrustedNetworks`; stored in plain slice `b.trustedNets`, assigned unlocked at `:131`, read per connection in `isTrustedSource` (`:139,149`) | HOT-1 |
| `smtp.tls.cert_file`, `.key_file` | `smtp/server.go:675-676` | ctor; loaded once, load failure only warns | RESTART |
| `smtp.tls.ca_file` | none | none | NO-OP |
| `smtp.limits.max_message_size` | `smtp/server.go:655` (`mx.MaxMessageBytes`), `:668` | ctor, copied into go-smtp server structs | RESTART (HOT-3 candidate) |
| `smtp.limits.max_recipients` | `smtp/server.go:656-658,669` | ctor, copied into go-smtp server structs | RESTART (HOT-3 candidate) |
| `smtp.limits.max_connections` | `smtp/server.go:689-691,705,728-730` | ctor; `netutil.LimitListener(…, s.maxConn)` fixes the cap at `Listen` | RESTART |
| `smtp.limits.flood_threshold` | `agent.go:440` and `:1243` -> `mail.NewRateLimiter` (`mail/ratelimit.go:18`; plain `limit` field read unlocked at `:28`) | ctor. The argument is named `msgsPerHour` | RESTART (HOT-3 candidate) |
| `smtp.limits.messages_per_minute` | `smtp/server.go:697` -> `newInboundRateLimiter` (`smtp/inbound_ratelimit.go:30`) | ctor; limiter has a plain `limit` field | RESTART (HOT-3 candidate) |
| `smtp.limits.max_connections_per_ip` | `smtp/server.go:696`, read at `:172` (`Backend.NewSession`) | ctor; plain `maxPerIP` int. Read at `:172` OUTSIDE `b.mu` (the mutex only guards `perIP`, taken at `:174`) | RESTART (HOT-3 candidate) |
| `smtp.limits.outbound_messages_per_minute` | `smtp/server.go:698`, used `:446-447` | ctor; as above | RESTART (HOT-3 candidate) |
| `smtp.limits.outbound_recipients_per_hour` | `agent.go` -> `mail.NewRateLimiter` stored as `Agent.RecipientLimiter` | ctor | RESTART |
| `smtp.limits.send_as_verify_max_per_hour` | `agent.go` -> `mail.NewRateLimiter` handed to the send-as verification handler (`SetLimiter`) | ctor | RESTART |
| `smtp.relay.enabled` | `smtp/relay.go:91` (`Relay.Deliver`) | ptr: read per delivery through `&a.Config.SMTP.Relay` (`agent.go:1239`) | RESTART in incr. 1 (HOT-3, see 4.3) |
| `smtp.relay.host` | `relay.go:91,98,101` | ptr, per delivery | RESTART (HOT-3) |
| `smtp.relay.username` | `relay.go:251,258` | ptr, per delivery. SECRET | RESTART (HOT-3) |
| `smtp.relay.password` | `relay.go:258` | ptr, per delivery. SECRET | RESTART (HOT-3) |
| `smtp.relay.allow_insecure_auth` | `relay.go:252` | ptr, per delivery | RESTART (HOT-3) |
| `smtp.relay.mta_sts_enabled` | `relay.go:41` (`NewRelay`) | ctor, decides whether a cache object exists | RESTART |
| `smtp.relay.dane_enabled` | `relay.go:44` | ctor, decides whether a resolver exists | RESTART |
| `smtp.relay.dnssec_resolver` | `relay.go:45` | ctor | RESTART |
| `smtp.dkim.selector` | `mail/dkim.go:44` (`NewDKIMSigner`), called `agent.go:1213` | ctor | RESTART |
| `smtp.dkim.domain` | `agent.go:585,1209,1235,1251,2414` | ctor; several derived values | RESTART |
| `smtp.dkim.private_key_file` | `mail/dkim.go:30,34` | ctor; key read once | RESTART |

`imap`, `pop3`

| Key | Consumer | How read today | Class |
|---|---|---|---|
| `imap.enabled` | `agent.go:1307` | ctor | RESTART |
| `imap.port`, `imap.port_tls` | `agent.go:1329-1330,1342-1343`; `agent.go:572-573` (autoconfig) | ctor | RESTART |
| `imap.proxy_protocol` | `agent.go:1345` | ctor (`IMAP.Listen`) | RESTART |
| `imap.max_connections` | `imap/server.go` `SetConnectionLimits` | `netutil.LimitListener` per listener, fixed at `Listen` | RESTART |
| `imap.max_connections_per_ip` | `imap/server.go` `SetConnectionLimits` | `netx.PerIPLimiter` shared by plain and TLS | RESTART |
| `pop3.max_connections` | `pop3/server.go` `SetConnectionLimits` | `netutil.LimitListener` per listener, fixed at `Listen` | RESTART |
| `pop3.max_connections_per_ip` | `pop3/server.go` `SetConnectionLimits` | `netx.PerIPLimiter` shared by plain and TLS | RESTART |
| `pop3.enabled` | `agent.go:1357` | ctor | RESTART |
| `pop3.port`, `pop3.port_tls` | `agent.go:1374-1375,1385-1386` | ctor | RESTART |
| `pop3.proxy_protocol` | `agent.go:1388` | ctor | RESTART |

`web`

| Key | Consumer | How read today | Class |
|---|---|---|---|
| `web.enabled` | none | none | NO-OP |
| `web.port` | `agent.go:937,1453,2635` | ctor | RESTART |
| `web.session_secret` | `agent.go:415` (copied into local `sessionSecret []byte`, then captured by auth, CSRF and internal-auth middleware), `agent.go:2597` (per request) | ctor plus per-request. SECRET. A change invalidates every session and CSRF token | RESTART |
| `web.tls.cert_file`, `.key_file` | `agent.go:501,949-950` | ctor; `tls.LoadX509KeyPair` once | RESTART |
| `web.tls.ca_file` | none | none | NO-OP |
| `web.https_redirect`, `web.http_redirect_port` | `agent.go:1447-1448` | ctor | RESTART |
| `web.plain_http` | `agent.go:505,947`; also forced true in dev at `agent.go:266` and by `--plain-http` (`cmd/bongo/agent.go:116-117`) | ctor | RESTART |
| `web.behind_tls_proxy` | `agent.go:510` | ctor, decides cookie `Secure` | RESTART |
| `web.source_url` | `agent.go` (router middleware `InjectSourceURL`) | ctor; target of the "Source code" link | RESTART |

`caldav`

| Key | Consumer | How read today | Class |
|---|---|---|---|
| `caldav.enabled` | none (CalDAV is registered at `agent.go:554` without reading it) | none | NO-OP |

`calendar`

| Key | Consumer | How read today | Class |
|---|---|---|---|
| `calendar.subscriptions.allow_private_networks` | `agent.go` Run (`netx.NewClient` for the subscription worker) | ctor; the safe client is built once | RESTART |

`antispam`

| Key | Consumer | How read today | Class |
|---|---|---|---|
| `antispam.builtin.enabled` | none (stage enablement comes from `pipeline.stage`) | none | NO-OP |
| `antispam.builtin.threshold` | TWO consumers. (1) `agent/antispam.go:50` -> `WithThreshold` -> `p.threshold` (`pipeline/antispam/builtin.go:37`), read at `:279`. (2) `agent.go:1092` -> `deliverProc.SetTraceHeaders` -> `p.spamThreshold` (`pipeline/deliver/deliver.go:74,104-106`), read via `effectiveSpamThreshold` (`:90`) at `:305` (X-Spam-Status header) and `:402` (Junk routing when no envelope override). The agent-role node has a THIRD copy: `agent/antispam.go:160` (`buildAgentAntispamProcessor`) | ctor into three separate plain `float32` fields | HOT-1 (as a pair with high_threshold) |
| `antispam.builtin.high_threshold` | `agent/antispam.go:51,161` -> `p.highThreshold` (`builtin.go:38`), read at `:277`. `SpamHighThreshold()` (`config.go:551`) clamps it to be >= the tag threshold. `pipeline/rescan.go:81` (comment) relies on high >= tag | ctor | HOT-1 (pair) |
| `antispam.rspamd.enabled` | `agent/antispam.go:71` | ctor | RESTART |
| `antispam.rspamd.url` | `agent/antispam.go:75` | ctor | RESTART |
| `antispam.spamassassin.enabled`, `.host`, `.port`, `.timeout`, `.threshold` | `agent/antispam.go:83-95` | ctor into `NewSpamAssassinProcessor` options | RESTART |
| `antispam.dnsbl.enabled` | `agent/antispam.go:128` (`dnsblOption`) | ctor | RESTART |
| `antispam.dnsbl.timeout`, `.cache_ttl` | `agent/antispam.go:141` -> `dnsbl.NewChecker` | ctor; the checker owns a per-IP cache for the life of the process | RESTART |
| `antispam.dnsbl.zone "<name>"` label `name` and `weight` | `agent/antispam.go:131-141` | ctor; weights map built once | RESTART |
| `antispam.dmarc_disabled` | `agent/antispam.go:57,164` | ctor, decides whether an evaluator is attached | RESTART |
| `antispam.dmarc_monitor_only` | `agent/antispam.go:58,165` | ctor | RESTART |

`antivirus`

| Key | Consumer | How read today | Class |
|---|---|---|---|
| `antivirus.clamav.enabled` | `agent/antivirus.go:36`; agent role `agent.go:2786-2788` | ctor | RESTART |
| `antivirus.clamav.socket` | `agent/antivirus.go:52-53` | ctor | RESTART |
| `antivirus.clamav.on_failure` | `agent/antivirus.go:41` (via `FailurePolicy()`, `config.go:685`) -> `WithOnFailure` -> `ClamAVProcessor.onFailure` (`pipeline/antivirus/clamav.go:55,96`), read at `:202` (`failureResult`) | ctor into one plain string-typed field; read per failed scan | HOT-1 |

`pipeline`, `queue`

| Key | Consumer | How read today | Class |
|---|---|---|---|
| `pipeline.workers` | `agent.go:1098,1111` -> `pipeline.WithWorkers`; worker goroutines are spawned at `Run` start (`pipeline/runner.go`, loop before `:88`) | ctor | RESTART |
| `pipeline.poll_interval` | `agent.go:1099` -> `runner.go:27`; consumed ONCE by `time.NewTicker(r.pollInterval)` at `runner.go:88` | ctor, then ticker fixed | HOT-2 (needs `Ticker.Reset` plumbing) |
| `pipeline.error_retention` | `agent.go` `startErrorPurge` -> `pipeline.RunErrorPurge` (`pipeline/errorpurge.go`), retention fixed at start | ctor | RESTART |
| `pipeline.quarantine_retention` | `agent.go` `startQuarantinePurge` -> `handlers.RunAutoPurge`, retention fixed at start (16.18) | ctor | RESTART |
| `pipeline.message_timeout` | `agent.go` -> `pipeline.WithMessageTimeout(MessageTimeoutDuration())` | ctor | RESTART |
| `pipeline.forward_max_per_hour` | `agent.go` -> `mail.NewRateLimiter` handed to `deliverProc.SetForwardLimiter` | ctor | RESTART |
| `pipeline.forward_verify_max_per_hour` | `agent.go` -> `mail.NewRateLimiter` handed to the forward verifier (`SetLimiter`) | ctor | RESTART |
| `pipeline.stage "<name>"` label `name`, `enabled`, `backend` | `agent.go:1047-1073` builds the ordered `[]pipeline.Processor` once | ctor | RESTART (stage re-ordering and add/remove is out of scope) |
| `queue.poll_interval` | `agent.go:1257` -> `queue.WithPollInterval`; `queue/worker.go:40`, ONE `time.NewTicker(w.pollInterval)` at `:101` | ctor, then ticker fixed | HOT-2 (needs `Ticker.Reset` plumbing) |
| `queue.bounce_copy_postmaster` | `agent.go` -> `BounceGenerator.SetPostmasterCopy`, set once when the generator is built | ctor | RESTART |
| `queue.max_lifetime` | `agent.go` -> `queue.WithMaxLifetime`; read per failure by `Worker.handleFailure` | ctor | RESTART |
| `queue.max_retry_interval` | `agent.go` -> `queue.WithMaxRetryInterval`; caps `retryDelay` | ctor | RESTART |
| `queue.delay_warning_after` | `agent.go` -> `queue.WithDelayWarningAfter`; read per failure by `Worker.handleFailure` | ctor | RESTART |
| `queue.concurrency` | `agent.go` -> `queue.WithConcurrency`; sizes the per-poll semaphore | ctor | RESTART |

The queue worker runs on the Raft leader only, so the four `queue.*` limits above follow whichever node is leader. Keep them identical on every voter: with differing values the bounce policy changes on a leader change. A mixed-version cluster behaves the same way, since a pre-upgrade leader bounces on attempt 10 rather than by lifetime. Messages already queued are judged by `created_at`, so one pending longer than `max_lifetime` bounces on its next failed attempt after the upgrade; admin "Retry now" does not reset `created_at`.

`telemetry`

| Key | Consumer | How read today | Class |
|---|---|---|---|
| `telemetry.prometheus.enabled`, `.port` | none (metrics are served on the web router at `/metrics`, `agent.go:408`) | none | NO-OP |
| `telemetry.log.level` | `cmd/bongo/agent.go` `runServe` (`parseLogLevel`) -> `newServeLogger`, which holds it in a `*slog.LevelVar` stored on `Agent.LogLevel` (16.7) | ctor | HOT-1 |
| `telemetry.log.format` | `cmd/bongo/agent.go:186-190` | ctor, picks the handler type | RESTART |
| `telemetry.log.file` | `cmd/bongo/agent.go:129` | ctor, opens a lumberjack writer | RESTART |
| `telemetry.log.max_size_mb`, `.max_backups`, `.max_age_days`, `.compress` | `cmd/bongo/agent.go:130-135` | ctor | RESTART |

### 4.2 Keys with no reader (NO-OP)

The NO-OP keys are those listed in `noopKeys` in `internal/config/diff.go`.
They are parsed and then never read in non-test code:

- `telemetry.prometheus.enabled`, `telemetry.prometheus.port`
- `antispam.builtin.enabled`
- `caldav.enabled`
- `web.enabled`
- `cluster.raft.data_dir`
- `server.datacenter`
- `smtp.tls.ca_file`, `web.tls.ca_file`
- `storage.pebble.wal_dir`

`storage.pebble.cache_size`, `pipeline.error_retention` and
`pipeline.quarantine_retention` were NO-OP at `b2eb0b9`; each now has a reader
at startup and is classified RESTART.

Consequences for reload:

- Changing them is a no-op both now and after reload, so the reloader does not
  report them as needing a restart (that would imply a restart helps). They
  are listed under `no_effect` in the `config reload complete` summary; there
  is no separate log line for them. Whether to remove them from the schema is
  a separate cleanup and out of scope here.
- `TestEveryConfigLeafIsClassified` (`internal/config/diff_test.go`) fails if a
  config leaf is missing from the classification table, so a new key cannot
  silently go unclassified.

### 4.3 Notes on specific classifications

**Why the HOT-1 set is small.** Increment 1 ships only keys whose delivery
path is simple, whose hazard is understood, and whose failure mode is mild:
`telemetry.log.level`, `antispam.builtin.threshold` plus `high_threshold` (as
one pair), `smtp.trusted_networks`, `antivirus.clamav.on_failure`.

**`smtp.relay.*` is not hot in increment 1 even though `Relay` already reads
through a pointer.** That is precisely the hazard: the pointer targets
`a.Config`, so naive in-place mutation would make it "work" while being a data
race on strings (`Host`, `Password`) that `-race` would flag. Making it hot
means changing `Relay.cfg` to an `atomic.Pointer[config.SMTPRelay]` holding an
immutable copy, and swapping the whole struct so `Host`, `Username` and
`Password` can never be read from two different versions inside one delivery
(`sendToHost` reads `cfg` several times, `relay.go:251-258`; it must load the
pointer once). Deferred to increment 3.

**`storage.blob_gc` is deliberately held back.** `blobGCPass` already reads
the mode every tick and already discards the candidate set on a mode change
(`blobGCCandidatesAcrossModeChange`, `agent.go:1631`, written for exactly this
feature; its comment at `:1620-1630` and the test comment at
`blobgc_test.go:984` confirm it). So it is technically easy. It is still not in
increment 1 because flipping `off -> on` makes the process delete data
without a restart boundary, and a mistyped value normalises silently to
`"off"` (`BlobGCMode`, `config.go:134`). It deserves its own review: log the
old and new mode at WARN and require two clean dry-run passes first (already
the behaviour). Note that reading it requires a holder: `a.Config.Storage` must
not be mutated; the tick would read an `atomic.Pointer`/`atomic.Value` instead.

**`pipeline.stage` is restart-required even for `enabled`.** The stage list is
iterated once and turned into a `[]pipeline.Processor` (`agent.go:1047`).
Also, `antivirus` stage ordering carries a documented invariant
(`agent.go:1064-1068`). Not touched.

**`web.session_secret` is restart-required.** `sessionSecret` is captured by
value into route-registration closures (`agent.go:415` and the `Use` sites at
`:645,755,1128`), and the per-request read at `:2597` signs peer requests, so
rotating it live would split nodes and invalidate every cookie. Never log it.

## 5. How each hot key reaches its consumer

All new values are built into immutable objects first, then published with a
single atomic store each. None of the following mutates `a.Config`.

### 5.1 `telemetry.log.level`: `*slog.LevelVar`

Implemented in 16.7. `newServeLogger` (`cmd/bongo/agent.go`) builds the
handler with a `*slog.LevelVar` (stdlib; implements `slog.Leveler`; `Set` is
atomic), set from `parseLogLevel(...)`, instead of the fixed `slog.Level` it
used before.
`newServeLogger` returns the `*slog.LevelVar`; `runServe` stores it on
`Agent.LogLevel` for the reloader, which must call `Set` on it and never swap
the pointer.

Downstream follows automatically:

- `logSinkHandler.Enabled` delegates to the wrapped base handler
  (`internal/web/handlers/logsink.go:72-73`), so the admin log viewer obeys the
  new level with no change.
- Child loggers created with `logger.With(...)` share the same handler and
  therefore the same `LevelVar`.
- The raft hclog bridge only partly follows. `cluster/raft.go:55` sets
  `raftCfg.LogLevel = "INFO"` and raft v1.7.3 `config.go:257` builds hclog at
  that level, so raft DEBUG/TRACE lines are filtered inside hclog before
  `slogWriter` sees them. Raising the slog level above INFO does filter raft
  lines; lowering it to DEBUG shows no raft debug output. Raft is deliberately
  unchanged.

Not covered, and stated so the doc is not read as "log level fully reloads":

- `observability.InstallGRPCLogger` fixes verbosity at 0 (`grpclog.go:36-37`)
  and `V(l)` compares against that fixed field (`:101`), so verbosity stays
  fixed. grpclog Info lines are emitted at slog DEBUG, so they do follow the
  `LevelVar`.
- `--log-level` shadows the file (section 2).

### 5.2 `antispam.builtin.threshold` + `high_threshold`: one shared holder

Hazard found in source: the tag threshold is copied into THREE places by value
(`builtin.go:37`, `deliver.go:74`, and a second builtin processor for the
agent role, `agent/antispam.go:160`). `deliver.go:63-78` states the invariant
that Junk routing and `X-Spam-Status` must never disagree, and
`pipeline/rescan.go:81` relies on high >= tag. Swapping the copies one by one
would break both for the interval between stores.

Design:

```go
// in internal/pipeline (consumer-neutral)
type SpamThresholds struct{ Tag, High float32 }   // immutable once published

type ThresholdSource interface{ Thresholds() SpamThresholds }
// implemented by a type wrapping atomic.Pointer[SpamThresholds]
```

- One holder per process, built from `Builtin.SpamThreshold()` and
  `SpamHighThreshold()` at startup (so the clamping rule `high >= tag`,
  `config.go:551-559`, is applied before publishing).
- The builtin processor and the deliver processor both take the holder
  (`WithThresholdSource` option; `SetTraceHeaders` loses its float argument and
  keeps the hostname) and each LOADS ONCE per message: `builtin.go:277-279`
  loads once before its `switch`; `deliver.go` loads once at the top of the
  per-message function and passes the value to both `buildSpamHeaders` (`:305`)
  and the routing comparison (`:402`).
- The agent-role node builds its own holder in `buildAgentAntispamProcessor`
  and registers it with the reloader too; a reloader on an agent-role node
  swaps only that holder.
- The existing constructor options (`WithThreshold`, `WithHighThreshold`) stay
  for tests and for callers that pass a constant.

Residual windows, stated honestly:

- A message already scored by the antispam stage under the old threshold and
  routed (`env.TargetMailbox = "Junk"` set at `builtin.go:281-282`) keeps that
  routing; deliver only consults the threshold when `TargetMailbox` is empty
  (`deliver.go:399-404`). So an in-flight message can have its Junk decision
  from the old pair and its `X-Spam-Status` stamp from the new one if the swap
  lands between the two stages of the same message. The window is microseconds
  (two stages in one worker) and the effect is a header, not a lost message.
- Delivery retry of the same message re-derives identical stamped bytes today
  (comment at `deliver.go:296-298`). A retry that straddles a swap stamps
  different bytes, hence a different blob hash. The old blob is reclaimed by
  mark-and-sweep GC; no correctness impact.

### 5.3 `smtp.trusted_networks`: `atomic.Pointer`

Existing hazard, quoted from source: `SetTrustedNetworks` is documented as
NOT safe after `Listen`/`Serve` because it writes an unsynchronised field that
sessions read from other goroutines (`smtp/server.go:115-130`). The field is a
plain `[]*net.IPNet` (`:76`), assigned at `:131`, read per connection at
`:139,149` (`isTrustedSource`, called from `inboundMeta`, `:421`).

Design:

- Change the field to `trustedNets atomic.Pointer[[]*net.IPNet]`.
- `SetTrustedNetworks` becomes `b.trustedNets.Store(&nets)`; `isTrustedSource`
  does one `Load()` and iterates that slice. A `nil` pointer means "no trusted
  networks" and preserves the fail-closed behaviour documented at `:134-137`.
- The published slice is never mutated after the store (the reloader builds a
  fresh slice from `SMTPConfig.ParseTrustedNetworks`, `config.go:196`).
- Update the setter's doc comment: remove "NOT safe after Listen".
- Both call sites keep working: server role `agent.go:1173`, agent role
  `agent.go:2751` (the latter is behaviourally inert today, comment at
  `agent.go:2742-2746`; it should still be registered with the reloader for
  correctness, but the doc must not claim it changes behaviour).
- Sessions already established are classified at connection time
  (`inboundMeta` evaluates per message with the connection's source IP, `:421`),
  so a narrowed list takes effect on the NEXT message, including on
  already-open connections. Say so in the release note.

Security: trusted networks are a relay-trust boundary (comment at
`:125-129` also notes the PROXY-protocol caveat). The reloader MUST log the old
and new CIDR sets at WARN as `config reload: smtp.trusted_networks changed`
with `old=[...] new=[...]`. CIDRs are not secret. Widening trust is the risky
direction; consider (open question, section 8) requiring the operator to
confirm widening via a second signal. This design does not.

### 5.4 `antivirus.clamav.on_failure`: atomic

`ClamAVProcessor.onFailure` is a plain field (`clamav.go:55`) written by the
option (`:96`) and read per failed scan at `:202` and `:207`. Change it to an
`atomic.Value`/`atomic.Pointer[OnFailure]` or `atomic.Int32` enum, with
`SetOnFailure(policy OnFailure)` for the reloader. `failureResult` loads once
and uses that single value for the `action` and the log line (it reads the
field twice today, `:202` and `:207`, which must collapse to one load).

The server-role processor and the agent-role processor are separate
instances (`buildAntivirusProcessor` called from `agent.go:1069` and
`:2786`); both must be registered with the reloader.

Fail-safe: `FailurePolicy()` (`config.go:685`) maps any unknown value to
`quarantine`; `Validate()` rejects unknown values (`config.go:765`), so a typo
fails the whole reload rather than coercing.

### 5.5 Poll intervals (increment 2, not 1)

`pipeline.poll_interval` and `queue.poll_interval` are copied into a field and
used exactly once in `time.NewTicker` at the start of `Run`
(`runner.go:88`, `queue/worker.go:101`). Writing the field changes nothing.
Hot reload needs `SetPollInterval(d)` that sends on a buffered channel (cap 1,
latest value wins) which the `select` loop handles with `ticker.Reset(d)`.
Reject non-positive durations at validation (`time.NewTicker` panics on
`d <= 0`; `PipelinePollInterval()` and `QueuePollInterval()` fall back to
defaults on a parse error instead, `config.go:803-833`, so the reloader must
validate the string itself and not rely on the accessor).

Queue delivery is leader-only (`worker.go:115`), so on a cluster only the
current leader's value matters; after a leader change the new leader's value
applies.

## 6. Reload flow

Trigger: SIGHUP, on its OWN `signal.Notify` channel, built by
`watchSignals(ctx, cancel, reload, logger)` in `cmd/bongo/agent.go`. It
registers both channels before returning: SIGINT and SIGTERM call `cancel()`,
SIGHUP calls `Agent.Reload` and never cancels. The returned `stop` calls
`signal.Stop` on both channels, cancels its inner context and waits for both
goroutines. `runServe` defers `stop` around `Run`; it is deliberately not run
on `ctx.Done`, so a SIGHUP or second SIGTERM during graceful shutdown is still
swallowed rather than restoring the default terminate action. Reload errors are
not logged again by the watcher: `Reload` logs its own failure.

Registration and reload (implemented): `registerSMTPBackend` and
`registerClamAV` take the reloader's lock (`Reloader.mu`, then `reloadMu`, the
order `Reload` uses) and apply the reloader's baseline, the current hot values,
to the consumer while joining the list. A reload therefore cannot land between
"registered" and "initial value set", and a consumer registered after a reload
starts on the reloaded value, not on `a.Config`. With no reloader they read
`a.Config`. The SMTP backends are built by `newServerSMTPBackend` and
`newAgentSMTPBackend`, which `Run` and `startSMTPAgent` call, so tests can see
registration.

Nil holders: a hot key whose holder is nil (`LogLevel`, spam thresholds; only
tests produce this) is dropped before apply with WARN `config reload: key has no
live consumer, not applied`. It is not listed under `applied` and its baseline
does not move.

Serialise: a `sync.Mutex` held for the whole reload. Two SIGHUPs arriving close
together run one after the other (or the second is coalesced; the channel has
capacity 1).

Steps. A failure in steps 1-3 aborts and leaves the running state untouched.

1. **Load** with the startup precedence (section 2): `config.LoadFile` on the
   pinned file, `config.ApplyOverrides` with the startup viper, then re-apply
   `--plain-http`. Shadowed keys are logged at this point.
2. **Validate**: on every reload, `merged.Validate()`,
   `merged.Antispam.DNSBL.Validate()` and
   `validateSessionSecret(role, web.session_secret)` (the same check `Run`
   applies), whether or not the relevant keys changed. `PipelineConfig.Validate`
   is deliberately not called: startup never calls it, so checking it on
   reload could stop a server that started successfully from ever reloading.
3. **Prepare all hot values** without publishing any: parse CIDRs
   (`ParseTrustedNetworks`), the threshold pair (applying the `high >= tag`
   clamp), the log level, the `on_failure` policy. Any error aborts.
4. **Diff** the new config against the baseline snapshot (section 2) with the
   pure function `config.Diff(old, new *Config) (hot, restart, noop
   []config.KeyChange)`. It walks the struct by reflection on leaf fields and
   uses the classification table as data. A `KeyChange` is `{Key string;
   Secret bool}` and never carries a value. A changed key missing from the
   table is reported as restart and secret.
5. **Apply** each changed hot key by its dedicated atomic store (section 5).
6. **Report restart-required keys**: for each changed key classified RESTART,
   log at WARN with msg `config reload: key needs restart` and attributes
   `key` and `secret` (bool). Values, old or new, are never logged.
7. **Summary** at INFO, msg `config reload complete`, attributes `file`,
   `applied`, `needs_restart`, `no_effect`, `shadowed` (lists of key names),
   `file_mtime` (RFC 3339, UTC) and `file_size` (bytes) of the file as read. A
   reload with no changes logs the same message with empty lists.
8. Replace the baseline snapshot with the new config ONLY after step 5
   succeeded. Restart-required keys stay "changed" relative to what the process
   is actually running, so the baseline for those keys must remain the
   running value, not the file's value; otherwise a second SIGHUP would stop
   warning about a key that still needs a restart. Implementation: the
   baseline is the config the process is running on, with only the applied hot
   keys updated.

Failure: any error logs ERROR with msg `config reload failed` and the error,
and the running state is unchanged (steps 1-3 touch nothing; step 5 consists
of stores that cannot fail once the values are prepared).

### Atomicity, stated honestly

Step 5 is several independent atomic stores, not one transaction. Because every
value is prepared and validated first, and a store cannot fail, the only
inconsistency is a mixed state between INDEPENDENT keys for roughly
microseconds, for example the new log level and the old trusted networks. Keys
that must move together do move together: the threshold pair is a single
pointer and is never observed half-updated. Nothing in the hot set has a
cross-key invariant other than that pair.

### Secrets in logs

Never log the value of a secret key: `smtp.relay.password`,
`smtp.relay.username`, `web.session_secret`, `cluster.gossip.encryption_key`
(`secretKeys` in `internal/config/diff.go`). The reloader never logs any
config value on the restart path: the WARN line carries `key` and `secret`
only, for secret and non-secret keys alike. The only values it logs are the
old and new CIDR sets for `smtp.trusted_networks` (section 5.3), which are not
secret. The classification table carries a `Secret` flag per key so callers
can redact anything they add; a new key whose name contains `secret`, `password`,
`key` (as in `encryption_key`, but not `private_key_file`, which is a path) or
`token` fails the classification test until it is flagged or explicitly
exempted.

Error strings are the second leak path. What I verified in hcl/v2 v2.24.0:
`hclsimple.DecodeFile` returns `hcl.Diagnostics` (`hclsimple.go:88-110`) whose
`Error()` is `"<Subject range>: <Summary>; <Detail>"` (`diagnostic.go:101-117`)
with no source snippet, so the file's text is not echoed wholesale. What I did
NOT verify is that no individual `Detail` string embeds an attribute value
(parser and type-conversion messages are produced in several packages, and I
did not audit each). Therefore:

- Log an `hcl.Diagnostics` error as `subject` (file:line,col) and `summary`
  only, never `Detail`. The operator has the file; the position is enough.
- `Validate()` and the `Parse*` helpers produce our own strings. The ones that
  exist at `b2eb0b9` echo `server.role`, a CIDR, an `on_failure` value, a
  DNSBL zone name and numbers (`config.go:205,718,766,503`), none secret. A
  redaction test (task (f)) puts distinctive sentinel strings into every
  secret key, forces each validation error path it can, and asserts the
  captured log output never contains a sentinel. That test is what keeps a
  future error message from leaking.

### Signal semantics: what SIGHUP does today

- SIGHUP now reloads the config and no longer terminates the process.
  `watchSignals` registers a handler for it, so the Go runtime's default
  action (exit on SIGHUP) no longer applies. Before this change, a SIGHUP
  terminated `bongo`.
- In-container: `bongo` is the image's `ENTRYPOINT`, so it runs directly
  as the container's main process (PID 1) as uid 10001, with no wrapper
  script, and receives the signal itself.
- Under systemd: `deploy/bongo.service` has
  `ExecReload=/bin/kill -HUP $MAINPID`, so `systemctl reload bongo`
  triggers a reload.
- Docker: `docker compose kill -s HUP bongo` delivers it.
- Terminal: a foreground `bongo serve` also receives SIGHUP when its
  controlling terminal closes. After this change that closes the terminal
  without stopping the server. That is a behaviour change worth a line in the
  release note.
- Docker single-file bind mounts: `deploy/docker-compose.yml:74` mounts
  `./bongo.prod.hcl:/etc/bongo/bongo.hcl:ro` as a single file. Editors that
  replace a file by writing a new inode and renaming leave a single-file bind
  mount pointing at the old inode. This is general Docker behaviour that I
  have not tested against this stack; the deployment doc for 16.7 should
  say "edit in place or verify with `docker compose exec bongo cat
  /etc/bongo/bongo.hcl` before sending SIGHUP". The `config reload complete`
  line logs `file_mtime` and `file_size` of the file as read, so a stale read
  is visible by comparing them with the edited file.

## 7. Cluster considerations

Config is per-node. It is read from a local file at startup
(`LoadWithDiscovery`) and is not stored in Pebble or the Raft log; no
`RaftCommand` carries config. So:

- SIGHUP applies to ONE node. In a multi-node cluster the operator must send it
  to every node, and until they have, nodes run different hot values. For
  example, two nodes can score the same sender differently because their spam
  thresholds differ, or accept relay from different networks.
- Queue delivery is leader-only (`queue/worker.go:115`), so for
  `queue.poll_interval` the leader's value is the one that matters.
- Agent-role nodes run their own antispam processor
  (`buildAgentAntispamProcessor`, `agent/antispam.go:158`) and their own
  antivirus processor (`agent.go:2786`). Those are separate in-process
  instances that the reloader on that node must also update. The server does
  not push thresholds to agents.
- Restart-required keys include everything that must agree across nodes
  (`cluster.*`, `server.name`, ports, TLS), which is why the restart class is
  the safe default.
- Nothing in this design detects divergence between nodes. A follow-up could
  expose a config fingerprint (hash of non-secret keys) on the existing
  health or cluster-status endpoint so divergence is visible. Out of scope.
- See `docs/multi-node-cluster-checklist.md`: its pre-flight gate
  (`Config.Validate`, "refuses to start") applies at startup, and reload must
  run the same validation, so a reload cannot weaken it. The multi-node gate
  keys (`cluster.join`, `cluster.gossip.encryption_key`, `cluster.tls.*`)
  are all RESTART, so reload can neither enable nor disable cluster
  transport security.

## 8. Out of scope, risks, open questions

Out of scope for 16.7 (all remain restart-required):

- TLS certificate and key hot reload (SMTP, web, IMAP, POP3, raft).
  `deploy/README.md` already tells operators to restart after a renewal.
  Likely future approach is `tls.Config.GetCertificate`; separate design.
- Listener rebinds and port changes.
- Pipeline stage add, remove or re-order, and worker count changes.
- DKIM key and selector changes (per-domain keys already have an admin UI
  path through the registry).
- `web.session_secret`, `server.role`, `server.name`, anything under
  `cluster.*`, `storage.data_dir`.
- Log format, log file path and rotation settings.
- Removing the NO-OP keys from the schema.
- Cross-node config distribution or divergence detection.
- Reload via HTTP endpoint or CLI subcommand (SIGHUP only; an HTTP trigger
  would need the "`/internal/*` is not a security boundary" guardrail
  applied).
- Re-reading `bongo.env` (process environment is fixed).

Risks:

1. Line drift with 16.5 (cited by symbol).
2. Override-precedence regressions (section 2). Mitigated by keeping the
   startup viper and a test per override.
3. Hidden second consumers of one key: the spam threshold has three; mitigated
   by the shared holder and by the classification test enumerating consumers in
   comments. A fourth consumer added later would not be updated: add a test
   that fails when `SpamThreshold()` is called outside the holder constructor.
4. In-place mutation of `a.Config` would be a data race (section 3). A
   `-race` test that runs a reload while SMTP, pipeline and queue run is part
   of 16.7.
5. Trusted networks are a security boundary; widening takes effect on the next
   message of established connections (section 5.3).
6. Poll intervals are not field swaps (section 5.5); claiming them hot without
   ticker plumbing would be false.
7. Secret leakage via error strings (section 6).
8. `docker kill -s HUP` against a stale single-file bind mount reloads old
   content (section 6).
9. Behaviour change: SIGHUP stops terminating the process.
10. Dev role: `NewAgent` mutates `PlainHTTP` (section 2); the baseline is
    taken before it.

Open questions for the operator:

- Should widening `smtp.trusted_networks` require extra confirmation, or is a
  WARN log with old and new sets enough?
- Should `storage.blob_gc` become hot in a later increment, given it changes
  whether data is deleted?
- Should NO-OP keys be removed (breaking for config files that set them, since
  `hclsimple` rejects unknown attributes) or kept and documented? A removal
  would make existing `bongo.prod.hcl` files fail to decode, so that is a
  deployment-affecting change.

## 9. Increments and ordered task list for 16.7

Prerequisite: 16.5 merged (so `Validate` is wired at startup and the file's
current shape is stable), and this design approved.

First increment ships exactly these four keys:

1. `telemetry.log.level`
2. `antispam.builtin.threshold` and `antispam.builtin.high_threshold`, as a pair
3. `smtp.trusted_networks`
4. `antivirus.clamav.on_failure`

Every other changed key is reported as needs-restart (or no-effect). Increment
2: `pipeline.poll_interval`, `queue.poll_interval`. Increment 3: `smtp.relay.*`
credentials/host, SMTP limits, `storage.attachment_dedup_min_size`, and
(separately reviewed) `storage.blob_gc`.

Each task is small, independently testable, and mergeable on its own. The
test named is the one that must go red when the implementation is broken;
mutation-check each.

- **(a) Log level holder.** `newServeLogger` uses a `*slog.LevelVar` and
  returns it. Test: build the logger, assert `Enabled(Debug)` is false at
  info, call `Set(Debug)`, assert it is true, and assert the sink wrapper
  follows (`logSinkHandler.Enabled`). Mutation: replace `LevelVar` with a copy
  of the value; test goes red.
- **(b) Atomic trusted networks.** `Backend.trustedNets` becomes an
  `atomic.Pointer`. Test: under `-race`, call `SetTrustedNetworks` in a loop
  concurrently with `isTrustedSource` (and one `NewSession`/`inboundMeta` path),
  asserting no race and fail-closed on `nil`. Mutation: revert to the plain
  field; `-race` reports a race.
- **(c) Shared threshold holder.** Add `SpamThresholds` and the holder; wire
  builtin processor, deliver processor and the agent-role builder to it;
  `SetTraceHeaders` drops its threshold parameter. Test: publish a new pair
  and assert (i) the builtin processor tags at the new tag and quarantines at
  the new high, (ii) the deliver processor's Junk routing and `X-Spam-Status`
  both use the new tag value, (iii) after one publish both observe the same
  pair under `-race` with concurrent readers. Mutation: leave deliver on the
  old copy; test (ii) goes red. Update `rescan.go:81`'s comment if the
  invariant text changes.
- **(d) Atomic ClamAV policy.** `onFailure` becomes atomic with
  `SetOnFailure`; `failureResult` loads once. Test: set `accept`, assert `pass`;
  set `quarantine`, assert `quarantine`, with a `-race` concurrent setter.
  Mutation: make `failureResult` read twice with a flip in between; test goes
  red.
- **(e) Pure diff and classification.** `config.Diff(old, new *Config) (hot,
  restart, noop []config.KeyChange)`, where `KeyChange` is `{Key, Secret}`,
  driven by a classification table that includes a `Secret` flag. Table-driven test that reflects over EVERY leaf field of
  `Config` and fails if any field is unclassified (mirroring
  `knownBlobBearingFields` in `internal/agent/blobref_enumeration_test.go`),
  plus cases for the pointer blocks (`Queue`, `AgentServer`, `SpamAssassin`,
  `DNSBL`), repeated blocks (`Stages`, `Zones`) and secret flagging.
  Mutation: add a field without classifying it; test goes red.
- **(f) Reloader.** In `internal/agent` (or a small `internal/reload`
  package): `Reload(ctx)` runs load, validate, prepare, diff, apply, report in
  that order under a mutex. Tests: (i) a failing `Validate` leaves every holder
  unchanged (feed input that would otherwise be accepted: a valid log level
  change PLUS an invalid CIDR, assert the log level did NOT change); (ii) a
  restart-required change logs one WARN `config reload: key needs restart` and
  changes nothing; (iii) secret redaction: sentinel values in every secret key
  never appear in captured logs, including on error paths; (iv) a flag-shadowed
  key logs shadowed and does not apply; (v) a second reload after a
  restart-required change still warns (baseline rule, step 8); (vi) a
  reload under `-race` while holders are being read.
- **(g) SIGHUP wiring (done, 16.13; see section 6 for the final shape).** In `cmd/bongo/agent.go`: a separate
  `signal.Notify(hupCh, syscall.SIGHUP)`, goroutine calling the reloader, torn
  down with the context. Test: send SIGHUP to the test process (via the
  extracted wiring function) and assert the reload ran and `ctx` was NOT
  cancelled; send SIGTERM and assert `ctx` is cancelled. Mutation: add SIGHUP to
  the existing channel; the first assertion goes red.
- **(h) Deployment (done, 16.13).** `deploy/bongo.service`: add
  `ExecReload=/bin/kill -HUP $MAINPID`. `deploy/README.md`: document `docker
  compose kill -s HUP bongo`, the bind-mount caveat, that env/flag overrides
  win, that `bongo.env` needs a restart, and the per-node rule. No Go test; a
  doc check only.
- **(i) End-to-end check, by the orchestrator, not a worker.** One
  integration test: start a dev-role agent, change the spam threshold in the
  config file, send SIGHUP, deliver a message that scores between the old and
  new thresholds, and assert it lands in the mailbox the new threshold
  dictates. This runs once in the integration gate after merge, per the
  parallel-worker rule.

Increment 2 tasks (poll intervals) and increment 3 tasks (relay, limits,
blob_gc) get their own entries in `prds/TASKS.md` after increment 1 ships; each
follows the same prepare-then-apply pattern and adds its rows to the
classification table (flipping the class) with a test.
{% endraw %}
