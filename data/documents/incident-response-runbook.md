# Incident Response Runbook

> **Fictional document.** This runbook was written for the
> `local-docs-rag-assistant` demo and is licensed under
> [CC BY 4.0](../README.md). It describes an invented platform.

## 1. Severity levels

| Severity | Definition | Examples |
|----------|------------|----------|
| Sev1 | Complete outage or risk to customer data | Login unavailable for all tenants; suspected data exposure |
| Sev2 | Degraded service or a single region affected | Elevated errors in one region; one integration unavailable |
| Sev3 | Minor or no customer impact | Cosmetic bug; internal tooling degraded |

When in doubt, start at the higher severity. Downgrading later is cheaper than a
late response to a real outage.

## 2. Roles

Every incident has three roles:

- **Incident Commander (IC):** owns coordination, decisions and the timeline.
  The IC **does not debug**; debugging is delegated so the commander keeps the
  full picture.
- **Communications Lead:** owns the status page, stakeholder updates and the
  customer-facing wording.
- **Scribe:** records timestamps, hypotheses, actions and decisions in the
  incident channel.

One person may hold more than one role in a Sev3, but Sev1 and Sev2 require a
dedicated IC.

## 3. First 10 minutes

1. Declare the incident and state the suspected severity.
2. Open the incident channel and pin this runbook.
3. Assign the IC, Communications Lead and Scribe.
4. Open the service dashboards and the error-tracking view.
5. Start the timeline with the detection time and the first symptom.
6. Publish an initial status update.
7. Create the follow-up ticket.

Do not wait for a root cause to publish the first update. State what is known,
what is affected and when the next update will arrive.

## 4. Communication cadence

- **Sev1:** publish on the status page within **15 minutes** of declaration and
  post an update **every 30 minutes** until resolution.
- **Sev2:** post an update **every 2 hours**.
- **Sev3:** provide a written summary within **2 business days**.

Updates must include impact, current mitigation, and the next update time. Avoid
speculation and internal jargon in customer-facing messages.

## 5. Database failover

A replica may be promoted only when **replication lag is less than 5 seconds**.
The failover target is **120 seconds** from the decision to promote.

```bash
gatewayctl db status --region <region>
gatewayctl db promote --region <region> --confirm
gatewayctl db status --region <region>
```

After promotion, keep the old primary **offline for 30 minutes** so that it cannot
accept writes while the new topology converges. Update the connection strings
through the configuration service, not by editing pods directly.

If lag is above the threshold, do not promote. Escalate to the database on-call
engineer and continue investigating.

## 6. Escalation

| Situation | Contact |
|-----------|---------|
| Replication, storage or query performance | Database on-call via `#db-oncall` |
| BGP, DNS or packet loss | Network on-call via `#network-oncall` |
| Suspected breach or credential leak | Security immediately, then the IC |
| Vendor outage | Vendor support plus the Communications Lead |

Security incidents bypass the normal severity queue. When in doubt, contact
Security first and let the IC classify later.

## 7. Change freeze

During a Sev1, no production deployment is allowed except a fix approved by the
Incident Commander. The approval, target version and rollback plan are recorded
in the incident channel. A freeze does not block read-only diagnostics.

## 8. Postmortem

The postmortem draft is due within **5 business days** of resolution. The review
meeting happens within **10 business days**.

A good postmortem is blameless and includes:

- A factual timeline with timestamps.
- Contributing factors, not a single "root cause" if several interacted.
- Customer impact and duration.
- What went well and what slowed the response.
- Action items with an owner and a due date.

Action items such as "be more careful" or "improve monitoring" are rejected. Each
item must name a concrete change, an owner and a verifiable completion criterion.

## 9. Closing the incident

Close only when the customer impact has ended, monitoring is stable for at least
30 minutes, and follow-up work is tracked. The IC announces the close and hands
the timeline to the postmortem owner.
