# Evaluation set

`questions.jsonl` contains 24 manually written questions about the four
documents in `../data/documents/`. It is committed to make the evaluation
reproducible and auditable.

## Schema

One JSON object per line:

```json
{"id": "v01", "split": "validation", "question": "How often ...?", "expected_source": "edge-gateway-operations.md", "expected_page": null, "key_facts": ["every 15 seconds", "2 second timeout"], "is_answerable": true}
```

| Field | Type | Meaning |
|-------|------|---------|
| `id` | string | Unique identifier, e.g. `v01` / `t01`. |
| `split` | string | `validation` or `test`. Fixed before tuning. |
| `question` | string | Question asked exactly as written. |
| `expected_source` | string or null | Filename that supports the answer; `null` for unanswerable questions. |
| `expected_page` | integer or null | Page for PDFs; `null` for Markdown/TXT or unanswerable questions. |
| `key_facts` | list[string] | Facts a citation must support for the answer to count as grounded. |
| `is_answerable` | boolean | `false` means the corpus does not contain the answer. |

## Split

- **Validation:** 9 answerable + 3 unanswerable — used only to choose the
  similarity threshold.
- **Test:** 9 answerable + 3 unanswerable — used only for the final report.

Unanswerable questions were checked against the corpus: the information is
genuinely absent, not merely hard to find.

## Commands

All commands run from the repository root with the virtual environment active.

```bash
# Retrieval only, no chat model needed (fast sanity check)
python eval/evaluate.py --rebuild --retrieval-only

# Choose the similarity threshold on validation (retrieval only)
python eval/evaluate.py --tune-threshold

# Final run: retrieval + answers, validation and test
python eval/evaluate.py
```

Results are written to `reports/` (gitignored):

- `eval_validation.csv`, `eval_test.csv` — one row per question.
- `summary_validation.json`, `summary_test.json` — aggregate metrics.
- `threshold_tuning.json` — the validation table and the selected threshold.

## Metrics

| Metric | Definition |
|--------|------------|
| `retrieval_top1` | Expected source (and page for PDFs) is the first retrieved chunk. |
| `retrieval_top3` | Expected source appears in the top-3 retrieved chunks. |
| `citation_source_match` | At least one cited chunk comes from the expected source/page. |
| `auto_supported` | Automated proxy: answer not abstained, cites the expected source, and 100% of `key_facts` tokens appear in the cited passages. |
| `abstention_unanswerable` | Unanswerable questions answered with the abstention message. |
| `median_latency_ms` | End-to-end retrieval + generation time. |

The automated `auto_supported` metric is not a substitute for reading the
answers. To do the manual check described in the specification, fill
`supported_human` for answerable rows and `correct_abstention_human` for
unanswerable rows with `yes` or `no`, then run:

```bash
python eval/evaluate.py --summarize reports/eval_test.csv
```

The summary reports manual rates only for rows that were actually filled.

## Initial targets (test split)

- Correct source in top-3 for at least 7/9 answerable questions.
- At least 7/9 answerable answers supported by their citations.
- At least 2/3 unanswerable questions answered with abstention.

The threshold is chosen on validation only. If the test result misses a target,
report and analyze the failure; do not retune on test.

## Reference run

The committed reference run, including the validation threshold table and the
one test failure (`t07`), is documented in
[`../docs/evaluation.md`](../docs/evaluation.md).
