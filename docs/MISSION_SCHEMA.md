# Mission schema

Missions are YAML files in `inference_lab/missions/data/`, validated by the Pydantic models in
`inference_lab/missions/schema.py` at load time (`extra="forbid"` everywhere, so typos fail loudly).
The same files drive Observe, Guided and Expert modes. Adding a mission needs no code.

## Mission

| Field | Type | Notes |
|---|---|---|
| `id` | `m0N-slug` | Stable identifier, used in progress and placeholders |
| `number` | int | Display and ordering |
| `version` | semver | Bump when checks change |
| `title`, `tagline` | Loc | `{en: …, zh-TW: …}` — both languages are mandatory |
| `objectives` | Loc[] | What the learner can do afterwards |
| `prerequisites` | mission ids | Must be complete (verified by checks) before unlock |
| `concepts` | concept ids | Must exist in `tutor/knowledge/concepts.yaml` (tested) |
| `references` | registry ids | Must exist in `research/registry.yaml` (tested) |
| `steps` | Step[] | See below |
| `challenge` | optional | Same action + checks, no walkthrough and no hints; needed for "independent" mastery |
| `optional_experiments` | Loc[] | Ideas to go further |
| `completion_evidence` | Loc | Human-readable statement of what proves completion |

## Step

| Field | Notes |
|---|---|
| `id`, `title`, `what`, `why`, `expected`, `failure` | Localized text |
| `concept` | Opens "Teach me this" |
| `action` | `{id, params, editable}` — `id` must be an allowlisted action; `editable` lists params the learner may change in Guided mode (Expert shows all) |
| `checks` | **Required for action steps.** Deterministic rules on the finished run (see below) |
| `quiz` | For knowledge steps: question, options, answer index, explanation. A step needs an action or a quiz |
| `hints` | Progressive, vague first. Hint use is recorded and lowers mastery |
| `sources` | `{file, symbol}` — the code that runs. Tests assert each file and symbol exists |
| `reproduce`, `alternatives` | The CLI command to run it yourself; other tools that do the same job |
| `optional`, `requires_capabilities` | Optional steps never block completion; a step whose capabilities are missing is shown as not available and runs as `NOT_RUN` |

## Checks

```yaml
- {id: live, description: {en: "Live measurement", zh-TW: "即時實測"}, path: run.provenance, op: eq, value: LIVE_MEASURED}
```

* `path` starts at `run.` (status, provenance, experiment_id, error…) or `result.` (the action's returned data).
* `op`: `eq ne gt gte lt lte exists truthy in len_gte contains`.
* A missing path is reported as "missing", never as passed.
* The AI tutor has no access to this mechanism. Completion is only written by `Progress.record_evaluation`
  (from a finished run) and `Progress.record_quiz` (from the server-side answer check).

## Placeholders

Params may reference evidence from earlier steps: `${m05-put-it-to-the-test:s2-baseline}` resolves server-side to
the experiment id recorded when that step was verified. If the step is not verified, the run fails visibly.

## Example

See `m05-put-it-to-the-test.yaml`: a knowledge check (quiz), a benchmark step with six checks
(ran, live, ≥3 trials, TTFT > 0, zero errors, record saved), and a second knowledge check.
