"""Generate the fictional sample PDF used by the RAG demo.

The content is original and licensed CC BY 4.0. Run from the project root:

    python tools/build_sample_pdf.py
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

OUTPUT = Path(__file__).resolve().parents[1] / "data" / "documents" / "open-systems-handbook.pdf"

PAGES: list[tuple[str, str]] = [
    (
        "Open Systems Handbook\nCaching, Backpressure and Operations",
        """Edition 2.1

A fictional technical handbook written for the local-docs-rag-assistant
portfolio demo. It contains no real company, customer or personal data.

License: Creative Commons Attribution 4.0 International (CC BY 4.0).
You may share and adapt this text with attribution.

Contents
  2. Caching
  3. Backpressure
  4. Observability
  5. Capacity planning
  6. Change management""",
    ),
    (
        "2. Caching",
        """The default caching pattern is cache-aside: the application reads the
cache, loads from the source on a miss, then writes the value back.

Write-through is reserved for reference data that changes less than once per
hour. Do not use write-through for user-generated content.

Every TTL receives 10% jitter. Without jitter, many keys expire at the same
moment and create a load spike.

Cache stampedes are prevented with single-flight: one request recomputes a
missing value while the others wait up to 2 seconds. If the wait expires, the
caller reads from the source directly.

Negative results may be cached for at most 30 seconds. Longer negative caching
makes recovery from a transient failure invisible to users.

Never cache 5xx responses.""",
    ),
    (
        "3. Backpressure",
        """Every worker owns a bounded queue with a capacity of 1,000 items.
Unbounded queues hide overload and turn it into latency and memory growth.

When the queue reaches 80% capacity, the worker rejects new work with HTTP 429.
The rejection is intentional load shedding, not an error to retry immediately.

Admission is also controlled by a token bucket that refills 100 tokens per
second and holds at most 200 tokens. A request without a token is rejected
before it reaches the queue.

When the system is saturated, shed work in this order:

  1. Health checks are never shed.
  2. Reads are shed before writes.
  3. Background jobs are paused first.

Record every rejection with a reason code. A rejected request is a successful
protection of the system, not a lost metric.""",
    ),
    (
        "4. Observability",
        """Monitor four golden signals: latency, traffic, errors and saturation.
Each dashboard shows p50, p95 and p99 latency; an average hides the experience
of the slowest users.

Trace sampling is 10% in normal operation. All error traces are retained.
Metrics are kept for 30 days, traces for 7 days and logs for 21 days.

Alerts must describe user impact and link to a runbook. A CPU alert without a
user-facing symptom is a capacity signal, not an incident.

Review dashboards after every incident. Remove panels nobody uses; a dashboard
that is too large to read during an incident has negative value.""",
    ),
    (
        "5. Capacity planning",
        """Capacity planning uses Little's Law: L = lambda x W, where L is the
number of items in the system, lambda is the arrival rate and W is the time
each item spends in the system.

Plan for 30% headroom above the forecast peak. Headroom absorbs traffic spikes,
deployment overlap and the loss of one availability zone.

Before launch, run a load test at 2x the expected peak. The test must include
the slowest dependency, not a mocked fast path.

Review capacity monthly and after any change that increases payload size or
fan-out. A forecast older than one quarter is not a forecast; it is a guess.""",
    ),
    (
        "6. Change management",
        """Changes affecting more than 5% of traffic require a feature flag. The
flag must have an owner and an expiry date; permanent flags become hidden
configuration.

The rollback target is 5 minutes from the decision to roll back. Rehearse the
rollback before the release, not during the incident.

The standard maintenance window is Tuesday, 03:00-05:00 UTC. Work outside the
window requires approval from the incident commander on call.

Emergency changes require incident commander approval and a follow-up review.
During a Sev1, the change freeze applies to everything except the approved fix.

Every change is recorded with its version, flag state and rollback decision.""",
    ),
]


def build(output: Path = OUTPUT) -> Path:
    document = pymupdf.open()
    for number, (title, body) in enumerate(PAGES, start=1):
        page = document.new_page(width=595, height=842)  # A4
        page.insert_text(
            (56, 48),
            f"OPEN SYSTEMS HANDBOOK  |  PAGE {number}",
            fontsize=8,
            fontname="helv",
            color=(0.35, 0.35, 0.35),
        )
        page.insert_textbox(
            pymupdf.Rect(56, 78, 539, 160),
            title,
            fontsize=20 if number == 1 else 18,
            fontname="hebo",
        )
        remaining = page.insert_textbox(
            pymupdf.Rect(56, 170, 539, 780),
            body,
            fontsize=10.5,
            fontname="helv",
            lineheight=1.35,
        )
        if remaining < 0:
            raise ValueError(f"Page {number} content does not fit: {remaining:.1f}pt overflow")
        page.insert_text(
            (56, 812),
            "Fictional sample corpus - CC BY 4.0 - local-docs-rag-assistant",
            fontsize=8,
            fontname="helv",
            color=(0.45, 0.45, 0.45),
        )

    document.set_metadata(
        {
            "title": "Open Systems Handbook - Caching, Backpressure and Operations",
            "author": "Esteban Vizcaino",
            "subject": "Fictional sample corpus for a local RAG demo",
            "keywords": "RAG, sample corpus, CC BY 4.0, fictional",
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(output, garbage=4, deflate=True)
    document.close()
    return output


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path} ({path.stat().st_size} bytes)")
