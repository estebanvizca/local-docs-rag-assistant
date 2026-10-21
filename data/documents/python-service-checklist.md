# Python Service Production Checklist

> **Fictional document.** This checklist was written for the
> `local-docs-rag-assistant` demo and is licensed under
> [CC BY 4.0](../README.md). It contains general engineering guidance, not
> company policy.

## 1. Runtime and dependencies

- Use **Python 3.11 or newer** for new services.
- Commit a lock file and install from it in every environment.
- Never deploy with an unpinned `latest` dependency.
- Pin the base container image by digest, not only by tag.

## 2. Configuration and secrets

Configuration comes from environment variables following the twelve-factor
model. Secrets are fetched from the secret manager at startup and kept in memory.
A `.env` file is acceptable for local development only and **must never be
committed**. The service fails fast when a required variable is missing; it does
not fall back to a development default in production.

## 3. HTTP clients

- **Connect timeout: 2 seconds.**
- **Read timeout: 10 seconds.**
- Retries: **at most 3 attempts**, using exponential backoff with jitter.
- Only retry idempotent requests, or requests protected by an idempotency key.
- Open a **circuit breaker after 5 consecutive failures** and keep it open for
  **60 seconds** before allowing a probe request.

Timeouts and retries must be configured in one place and shared by every client.
Unbounded retries are treated as a production defect.

## 4. Graceful shutdown

On `SIGTERM` the service must:

1. Stop accepting new requests.
2. Allow in-flight requests to finish for up to **30 seconds**.
3. Close database connections and flush telemetry.
4. Exit with status code 0.

Kubernetes sends `SIGKILL` after the termination grace period, so the grace period
must be longer than the shutdown budget.

## 5. Observability

- Emit structured JSON logs with a request ID, route, status and latency.
- Export the RED metrics: rate, errors and duration.
- The p95 latency SLO is **99.5% of requests under 300 ms over 30 days**.
- Sample **10% of traces** in normal operation and retain all error traces.

Every alert must link to a runbook and include a severity. An alert without an
action is noise and should be removed.

## 6. Resource limits

| Resource | Request | Limit |
|----------|---------|-------|
| CPU | 250m | 500m |
| Memory | 256Mi | 512Mi |

Services that exceed these limits need a documented load test before the limit is
raised. Memory limits are not a substitute for finding a leak.

## 7. Security

- Run as a non-root user with **UID 10001**.
- Mount the container filesystem read-only; write only to an explicit temporary
  volume.
- Scan dependencies **every Monday** and before each release.
- Never log tokens, passwords, cookies or personal data.
- Treat a suspected secret leak as a security incident, not a normal bug.

## 8. Testing

- Unit tests must cover failure paths, not only the happy path.
- Integration tests run against an ephemeral database created for the test run.
- Tests never use real customer data or production credentials.
- A flaky test is fixed or removed; it is not retried until it passes.
- The build fails if the test suite fails; there is no manual override.

## 9. Releases

Risky changes go behind a feature flag. Every release has a documented rollback
plan and a changelog entry. The team verifies the health checks and the error
rate immediately after deployment. A release is not complete until it has been
observed in production for at least one traffic cycle.
