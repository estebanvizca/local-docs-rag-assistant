# Nimbus Edge Gateway Operations Guide

> **Fictional document.** Nimbus is an invented product. This guide was written
> for the `local-docs-rag-assistant` demo and is licensed under
> [CC BY 4.0](../README.md). Version 4.2.

## 1. Scope

The Nimbus Edge Gateway terminates TLS, applies per-tenant rate limits and routes
requests to regional services. This guide describes the operational defaults that
on-call engineers need during an incident. It does not cover application code or
customer configuration.

## 2. Health checks

The gateway exposes two HTTP probes:

- `GET /healthz` is the liveness probe. It returns `200` while the process can
  serve requests.
- `GET /readyz` is the readiness probe. It returns `200` only when the gateway
  has a valid route table and at least one healthy upstream.

The orchestrator runs each probe **every 15 seconds** with a **2 second timeout**.
A gateway is marked unhealthy after **3 consecutive failed checks**. It is marked
healthy again after **2 consecutive successful checks**.

When a gateway is removed from the load balancer, it drains existing connections
for **30 seconds** before shutting down. Do not terminate the process earlier:
in-flight requests would fail without a response.

## 3. Rate limits

Rate limits are applied per API key and per region.

| Key type | Sustained limit | Burst bucket |
|----------|-----------------|--------------|
| Default API key | 600 requests per minute | 50 requests |
| Administrative key | 3,000 requests per minute | 200 requests |

The sustained window is **60 seconds**. When a client exceeds the limit, the
gateway returns HTTP `429` with a `Retry-After` header. Clients must honor that
header; retrying immediately extends the block.

## 4. Caching

The gateway caches two kinds of responses:

- **Configuration responses** for **300 seconds**.
- **Authorization decisions** for **30 seconds**.

The cache key is composed of **`tenant_id`, `region` and `route`**. It never
includes the user ID, so a cached authorization decision is shared by users with
the same role in the same tenant and region.

The gateway never caches HTTP `5xx` responses. Negative authorization decisions
are cached for at most **10 seconds** to limit the impact of a stale deny.

## 5. Logging

Every request produces one JSON line. The required fields are `request_id`,
`tenant_id`, `route`, `status` and `latency_ms`. Missing fields cause the log
entry to be rejected by the ingestion pipeline.

The `Authorization` and `Cookie` headers are redacted before the entry is written.
Logs are retained for **14 days in hot storage** and **90 days in archive
storage**. Legal holds can extend the archive retention, but they never shorten
the hot retention.

## 6. Deployments

Production changes use a canary release:

1. Send **10% of traffic** to the new version for **20 minutes**.
2. Compare error rate and p95 latency with the stable version.
3. Roll back automatically if the error rate exceeds **2%** or if p95 latency
   exceeds **800 ms**.
4. Continue the rollout only if both metrics remain within budget.

Standard deployment windows are **Tuesday and Thursday, 14:00–17:00 UTC**.
Deployments outside those windows require approval from the on-call manager.

## 7. Backups

The configuration database is backed up **daily at 02:00 UTC**. Backups are
retained for **35 days**. A restore drill is performed **quarterly** in a
non-production environment. The drill is not optional: an untested backup is
treated as missing.

## 8. Support escalation

| Severity | First response |
|----------|----------------|
| Sev1 | Page the on-call engineer within 15 minutes |
| Sev2 | Respond within 1 hour |
| Sev3 | Respond on the next business day |

The primary on-call handoff happens every **Monday at 09:00 UTC**. The outgoing
engineer must update the handoff notes before the handoff meeting.

## 9. Related documents

- `incident-response-runbook.md` for incident roles and communication.
- `python-service-checklist.md` for service-level production requirements.
- `open-systems-handbook.pdf` for caching, backpressure and change management
  patterns.
