# Evaluation report

This document records the evaluation behind the numbers in the project README.
It is a small, manually reviewed benchmark, not a claim of general accuracy.

## Setup

| Item | Value |
|------|-------|
| Corpus | 4 fictional source files, 33 chunks |
| Questions | 24 (18 answerable, 6 unanswerable) |
| Validation split | 9 answerable + 3 unanswerable |
| Test split | 9 answerable + 3 unanswerable |
| Embedding model | `nomic-embed-text` |
| Chat model | `llama3.2:latest` (3B) |
| Retrieval | top-3, cosine similarity |
| Threshold | 0.60, selected on validation only |
| Runtime | 8-core CPU, no GPU |
| Date | 2026-10-21 |

The test split was not used to choose the threshold, the prompt or any retrieval
parameter. The threshold table below comes from
`python eval/evaluate.py --tune-threshold`, which reads the validation split only.

## Threshold selection

| Threshold | Answerable top-3 hits | Unanswerable questions with evidence |
|-----------|------------------------|--------------------------------------|
| 0.50 | 9/9 | 3/3 |
| 0.55 | 9/9 | 2/3 |
| **0.60** | **9/9** | **1/3** |
| 0.65 | 8/9 | 0/3 |
| 0.70 | 7/9 | 0/3 |
| 0.75 | 4/9 | 0/3 |

The selection rule maximizes validation hits first, then minimizes evidence
retrieved for unanswerable questions, then prefers the more conservative
threshold. `0.60` keeps all nine answerable questions retrievable while removing
two of the three spurious-evidence cases. The remaining case (an unanswerable
question that still retrieves a related chunk) is handled by model abstention.

## Final results

| Metric | Validation | Test | Target |
|--------|------------|------|--------|
| Expected source is top-1 | 9/9 | 9/9 | — |
| Expected source is in top-3 | 9/9 | 9/9 | ≥ 7/9 |
| At least one citation points to the expected source | 9/9 | 9/9 | — |
| Answer supported by the cited passage (manual) | 9/9 | 8/9 | ≥ 7/9 |
| Correct abstention on unanswerable questions | 3/3 | 3/3 | ≥ 2/3 |
| Median end-to-end latency, answerable questions | 110.9 s | 82.0 s | — |
| Median end-to-end latency, all questions | 73.9 s | 80.3 s | — |

The automated lexical support proxy (`auto_supported`) produced the same result
as the manual review: 9/9 on validation and 8/9 on test. That agreement is
encouraging but not guaranteed in general; the manual column is authoritative.

Abstention latency varies because the pipeline skips the chat model when no
chunk passes the threshold. Questions that retrieve related evidence still pay
for a model call before the model declines to answer.

## Failure analysis

### `t07`: correct facts, wrong citation

Question: *How many retry attempts are allowed, and what backoff strategy is
required?*

The answer stated the correct values (3 attempts, exponential backoff with
jitter), but cited `python-service-checklist.md` chunk `[1]`, which contains the
end of the retry section and the graceful-shutdown section. The facts are in the
adjacent chunk `[2]`, which was also retrieved with the same similarity score.

This is a **citation-grounding failure**, not a knowledge failure. The current
answerer verifies that a citation marker exists and maps to a retrieved chunk;
it does not verify that the cited chunk actually contains each sentence's facts.
A sentence-level citation verifier that remaps or rejects unsupported citations
would address this class of error. Until then, the manual review column is what
catches it.

### What did not fail

- All nine test questions retrieved the expected source in the top-3.
- All six unanswerable questions abstained on both splits.
- No answer was discarded for missing citation markers.

## Reproduce

```bash
cd local-docs-rag-assistant
source .venv/bin/activate
python eval/evaluate.py --tune-threshold
python eval/evaluate.py
```

The commands write `reports/eval_validation.csv`, `reports/eval_test.csv`,
`reports/summary_validation.json`, `reports/summary_test.json` and
`reports/threshold_tuning.json`. Fill `supported_human` and
`correct_abstention_human` with `yes`/`no`, then run:

```bash
python eval/evaluate.py --summarize reports/eval_test.csv
```
