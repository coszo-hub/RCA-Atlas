# How RCA Atlas is evaluated

This is the method behind `python -m atlas_eval`. It explains what a standard
evaluation of a system like RCA Atlas looks like, which choices this harness
makes and why, and how to read and extend the results. The latest numbers are
in `results/<run>/report.md`. §8 summarises the 2026-10-08 baseline.

## 1. What is being evaluated

RCA Atlas is several systems behind one question box. Each needs its own
evidence that it works:

| Layer | What it does | Suite(s) | Kind of truth |
|---|---|---|---|
| Task routing | Decides what kind of task a question is and who answers it | `routing`, `quake_questions` | Hand-labelled questions |
| Retrieval | Finds corpus evidence (Graph-RAG hits, graph neighbours, tool hints) | `retrieval` | Gold chunk IDs from `model_eval/datasets/rca_eval_v1_gold.jsonl` |
| Answering | Writes a cited answer from the evidence (Gemini / Groq) | `answers` | Reference answers, gold sources and entities, LLM judge |
| Earthquake tools | Counts, filters, and histograms over the UW hypo71 catalog | `quakes`, `quake_questions` | Real catalog fixtures plus an independent reading of the catalog rule |
| Data-correction tools (Maleen's notes) | Gap/timing diagnosis, CCF and peak lags, dv/v, A-0-A/SCPR calibration, linear drift | `gaps`, `timing`, `dvv`, `pressure` | Synthetic records with an injected, known truth |
| Agent | Uses those tools from a plain request in a sandbox | `agent` (scripted oracle), `agent_llm` (Claude) | Known answers to the injected truth |

Every suite reports a headline metric with a 95 % interval and a target.
Suites on one axis are not averaged into a single "Atlas score". A mean over
unlike things hides the failures this harness exists to find.

## 2. The standard pieces of an evaluation

The structure below is common to research benchmarks (e.g. BEIR and MTEB for
retrieval, HELM-style capability suites) and to production LLM-evaluation
practice.

1. **A capability taxonomy.** List what the system claims to do (§1), then
   build one eval set per capability. A single mixed question set
   under-samples the rare but important tasks, such as a clock correction.
2. **Eval sets with stated provenance.** Each case says where its truth came from:
   - **Known-answer (injection–recovery) cases.** Take a realistic synthetic
     record, inject a fault or a signal of known size, and ask the tool to
     recover it. This is the standard way to validate geophysical processing:
     "resolution tests" in tomography, synthetic clock-error tests in
     ambient-noise timing work, and synthetic stretching tests in dv/v papers.
     It isolates the algorithm from data availability and gives error as a
     function of signal-to-noise ratio.
   - **Real fixtures with an independent oracle.** Real catalog files, with
     truth computed by a deliberately plain second implementation of the rule
     rather than by the code under test.
   - **Hand-labelled questions.** Routing and date-understanding labels,
     written before the rules that answer them.
   - **Gold references.** Required chunk IDs, sources, entities, and reference
     answers curated by the maintainers (`rca_eval_v1_gold.jsonl`).
   - **Agentic tasks.** A plain request, unseen files, and a checkable final
     answer.
3. **Dev/test separation.** Anything you tune against becomes a dev set. The
   routing rules were tuned on the `dev` half only (hash split on the question
   text) and are reported on `test`. Synthetic suites regenerate from seeds;
   when a tool is changed in response to a suite, the change must be justified
   from first principles (§8 lists each one), and a fresh seed range should
   confirm it.
4. **Freezing and versioning.** Datasets are JSONL files with a version in
   the name (`*_v1.jsonl`). Each run records the dataset SHA-256, the git
   commit and dirty flag, the endpoint, and the models (`provenance/*.json`).
   Never edit a released case in place. Add a `v2` file and keep `v1`
   runnable, so numbers stay comparable over time.
5. **Metrics matched to the job** (§3), each with a **confidence interval**
   (§4) and a **target** grounded in the physics or in the user need (§5).
6. **Failure analysis.** Every report lists misses and errors next to the
   numbers. A metric without its failing cases cannot be acted on.
7. **Regression gating** (§7): rerun on every change and fail when a
   headline drops below target or falls significantly against the previous
   baseline.

## 3. Metrics by axis

| Axis | Metric | Definition |
|---|---|---|
| Detection (gaps, calibration windows, clock jumps) | Precision, recall, F1 | Event-level greedy one-to-one matching of same-kind intervals that overlap within a tolerance (1.5 sample periods; ±2 h or one stack bin for jumps). Micro-averaged over cases. |
| Classification (error type, task route, timing kind) | Accuracy, macro-F1, confusion matrix | Macro-F1 weights every class equally, so rare tasks count. |
| Estimation (Δt, dv/v, drift rate, offsets) | Pass rate within tolerance; MAE; bias; RMSE | Bias (signed mean error) is reported separately because a biased estimator can have a low MAE. |
| Uncertainty calibration | 2σ coverage | Share of cases with \|error\| ≤ 2 × reported σ. It should be near 95 %; far below means the tool is overconfident. |
| Selective prediction | Coverage; accuracy on covered; "confidently wrong" rate | For tools allowed to decline (the timing pick-quality gate). A tool that says "too noisy" beats one that guesses. |
| Counting | Exact match | Counts are discrete; partial credit hides off-by-one bugs. |
| Retrieval | Hit@10, Recall@5/10, MRR, collection hit | Standard IR metrics against gold chunk IDs. |
| Answer quality | Judge correctness (0/1/2), support by evidence, citation validity, format compliance, gold sources and entities, invented numbers | Deterministic checks first; the LLM judge only for what cannot be checked mechanically. |
| Operations | Served on the first attempt; latency p50/p95; cost per task | Availability is part of quality for a public tool. |
| Agent | Task success, right tool, right tool first, calls per task, cost | Errors count as failures in the headline. |

## 4. Statistics

- **Proportions** use the Wilson score interval. Unlike the normal
  approximation, it stays inside [0, 1] at small n and at 0 % or 100 %.
- **Other statistics** (MAE, MRR, F1, pooled ratios) use a seeded percentile
  bootstrap over cases (2,000 resamples). Pooled quantities resample whole
  cases, so correlated items inside a case stay together.
- **Comparisons on the same cases** use paired tests: exact McNemar on
  discordant pass/fail pairs, and a paired bootstrap of the mean difference.
  Unpaired comparisons waste power and can mislead.
- **Sample size.** A 95 % Wilson half-width near 50 % is about ±1/√n: n = 30
  gives ±18 points, n = 100 gives ±10, and n = 400 gives ±5. A suite with
  n < 30 (for example the 21 agent tasks) can show a large problem but cannot
  rank two close systems. Treat its intervals as the honest limit.
- **Many metrics, one run.** Each suite reports several numbers. Read the
  headline as the pre-registered metric and the rest as diagnostics; do not go
  looking for the one metric that moved.

## 5. Targets and tolerances

Tolerances come from the measurement, not from the results:

| Quantity | Tolerance | Reason |
|---|---|---|
| Clock offset Δt | 0.125 s | One sample at the 8 Hz used by chronos |
| "Confidently wrong" Δt | > 0.5 s | Half the 1 s jump-trigger threshold in chronos `filter_and_triggers` |
| dv/v | 0.01 % + 10 % of \|dv/v\| | Typical published resolution of daily dv/v (~0.01 %) plus a relative term for large changes |
| Corrected pressure | 0.1 kPa RMS | ≈ 1 cm of seawater, the scale of geodetic interest at Axial |
| Drift rate | 0.1 kPa/yr | ≈ 1 cm/yr, the scale of interannual vertical deformation studied at Axial |
| Earthquake counts and histograms | exact | Integers |

Headline targets (90 % for most tool suites, 80 % for retrieval Hit@10, 98 %
for availability) are starting points for discussion with the science team.
They are not discovered from the data.

## 6. The LLM judge, and checking it

Correctness against a reference answer, and whether every claim is supported
by the retrieved evidence, need judgement. `atlas_eval judge` asks a fixed
model (Claude Haiku via the Claude Code CLI) a fixed rubric (`judge.py`) and
records its reason. Standard precautions:

- **Calibrate against people before trusting it.** `judge_calibration_sheet.csv`
  holds a seeded, blind sample of 20 answers. Two people grade it with the same
  rubric. Report Cohen's κ (judge vs each person, and person vs person); use
  the judge alone only if κ ≥ 0.6, and re-check when the judge model changes.
- **Keep the judge separate from the answerer.** The judge is a different
  model family from the Worker's Gemini/Groq answerers, which limits
  self-preference.
- **Prefer mechanical checks.** Citation validity, format, gold sources,
  invented numbers, counts, and every tool output are checked deterministically.
- **Know what the judge sees.** The public Worker response carries only
  280-character excerpts of each hit, while the answering model saw full
  chunks. "Supported by evidence" is therefore a lower bound; a fair support
  score needs the full evidence package from the private API.
- **Pin the judge.** A judge change is a new metric. Rerun the baseline with
  it before comparing.

## 7. Using it as a regression gate

1. `python -m atlas_eval run --suites offline` on every pull request touching
   `atlas_tasks`, the Worker's routing code, or the router rules. These suites
   are deterministic, need no network, and finish in about two minutes.
2. Live suites (`retrieval`, `answers`, `agent_llm`) run nightly or before a
   release. They cost money and quota, and they vary with upstream models.
3. Fail the gate when a headline falls below its target, or when McNemar /
   paired bootstrap against the last accepted baseline shows a significant
   drop (p < 0.05) on the same dataset version.

## 8. Baseline 2026-10-08: what the harness found

The full report, with intervals, figures, and every failing case, is
`results/2026-10-08-baseline/report.md`. The highlights:

**Routing (per-task priority).** The deployed Worker has four implicit routes.
On the held-out test questions it sends 16 % to the right task type, because
11 of the 15 tasks in Maleen's notes and the v1 set have no route at all (every
timing, dv/v, calibration, drift, gap, QA/QC, and status question falls into
the research prompt). The new rule-based router
(`atlas_tasks/router_rules.json`) scores 96 % [89 %, 99 %] on the same held-out
questions (McNemar p ≈ 1e-16). Each route names the tools that must produce
the numbers.

**Earthquake questions.** The Worker's `axialDayWindow` gets 31 % of the
count questions right and none of the range or magnitude questions. "between
2026-09-23 and 2026-09-24" counts only the 23rd. "since 2026-09-20" counts
only the 20th. "day before yesterday" counts yesterday. "above magnitude 1"
counts everything. "quakes" and "events" are not recognised. The new
`parse_quake_request` gets all 26. During the run the UW catalog host was
unreachable from both this machine and the Worker, and the Worker then returns
HTTP 503 for every count question instead of saying the live catalog is down.

**Retrieval** is strong: required evidence is in the top 10 for 96 % of
questions with gold chunks (MRR 0.90). The `/v1/tools` router, however,
returned **no tool hint for any question that needs a tool** (0/16).

**Answers.** 65 % of first attempts were served. The rest were HTTP 503s
from free-tier model quota, plus every earthquake-count question while the
catalog was down. After one slower retry, 92 % were served. The judge rates
79 % [66 %, 88 %] of answers at least partly correct against the reference,
just under the 80 % target; only 19 % are fully correct. Citations are always
valid and gold sources are cited 94 % of the time. Only 55 % follow the
prompt's plain-text rule: Gemini complies 19/21 times, but Groq GPT-OSS
120B, which answered 45 of 66 questions because Gemini's free quota ran out,
complies only 17/45 (Markdown `**` headings). On questions that need a tool or a computation, the system says it
cannot compute 63 % of the time. Otherwise it describes the tool instead of
running it, or states values the excerpts do not contain. The Worker executes
no tool except the live day count.

**Tools from the notes.** All are new in `atlas_tasks`. Earthquake
counts, filters, and histograms are exact on real and edge-case files. The
harness found that both shipping hypo71 parsers (the Python
`axial_agent_tools` and the Worker's JS) count a row with a non-numeric field
that the catalog rule excludes. Fault diagnosis separates data gaps from timing
errors on the synthetic fault model. Pressure calibration passes A-0-A in every
case and SCPR in most cases. The documented failure is three calibrations,
which cannot constrain a curved drift. A linear trend from one non-calibrating
gauge cannot tell drift from real uplift, which the confound subset
demonstrates.

**Changes made because of the evaluation.** Each change is justified on
principle, and before/after numbers are kept in
`results/2026-10-08-before-fixes/`:

| Finding | Change | Effect |
|---|---|---|
| Timing at low SNR gave confident garbage (Δt off by up to tens of seconds; jump F1 0.02) | Pick-quality gate at the noise-only 99th percentile (from noise-only simulations, not the eval cases), and an automatic fall-back from 1 h to 6 h to 1 day stacks | Confidently wrong hours fell to 0 %; jump F1 rose from 0.02 to 0.72; drift error fell from 0.175 to 0.014 s/day. Below SNR ≈ 0.1 the tool now declines instead of guessing |
| dv/v σ overconfident (2σ coverage 51 % MWCS, 17 % DTW) | Standard errors inflated for AR(1) residual autocorrelation | Coverage 64 % MWCS (still optimistic) and 100 % DTW (now conservative); stretching was already 99 % |
| SCPR corrected record off by tens of kPa near calibrations | Mask out to the valve edges, transient included | SCPR cases pass except where calibrations are too few |
| Linear drift biased by exponential settling (0/7) | Exponential + linear model chosen by BIC, with τ refined continuously (a grid-step τ misfit leaked into the rate on 90-day records) | 7/7; the reported σ still covers only 3/7, so it remains optimistic |
| Tidal constituents unresolvable on short records (K1/P1, S2/K2 need about 182 days) | Rayleigh criterion picks the constituents fitted, as in T_TIDE/UTide | Guards real data; the synthetic tides were already resolvable |
| Unreachable catalog day aborted the whole histogram | Report it as a missing day | Busiest-day agent task passes |
| MCP server crashed on NumPy integers and replied with `id: null`, so the agent hung forever | Plain-JSON conversion of every tool result; errors keep the request id | Found only by the LLM-agent suite; the scripted oracle bypasses JSON |
| LLM agent used the non-calibrating drift tool on A-0-A records | Sharper tool descriptions; the drift tool masks valve excursions and warns | Claude Haiku agent: 18/20 scored tasks → 21/21, then 20/21 on a rerun after the review fixes (it answered a fault family instead of the kind names asked for), at $0.03 a task |

A pre-landing code review then found, and the PR fixes with regression tests:
an output path could escape the sandbox (the `.npz`/`.png` suffix was added
after the path check, and writes followed symlinks); LAPACK messages could
corrupt the MCP stdout stream; one glitched or NaN timestamp could empty a
gap-filled series; stretching returned −2 % when the coda window was empty;
DTW memory and catalog fetches were unbounded; yearless dates in January
landed in the future; quantized plateaus were flagged as flatlines and
spikes; and errored eval cases dropped out of pass rates instead of failing
the scorecard row. Since cropping DTW to the coda, its pass rate is 62 %
(was 64 %).

## 9. Limits and threats to validity

- **Synthetic is not real.** Injection–recovery shows that an algorithm recovers
  what the generator injects. It cannot show that the generator resembles RCA
  data. The same author wrote both, so near-perfect scores on `gaps` mainly
  guard against regressions. The real-data sets below are the next step.
- **Single author.** The same person wrote the routing questions, labels, and
  rules (rules after questions, test half untouched). An independent labeller
  should extend `routing_v1` and `quake_questions_v1` before the numbers are
  quoted outside the team.
- **Live suites drift.** Worker answers depend on upstream free-tier models and
  quotas that change daily. Compare live runs only against runs made close in
  time, and read availability as part of the result.
- **Small n.** Agent (21), SCPR subsets (7–10), and quake questions (26) have
  wide intervals; the report shows them.
- **v1 gold set issues.** Of its `expected_tool` names, 11 do not exist (mapped
  in `suites/live.py::TOOL_ALIASES`), and two (`nereus_file_status`,
  `nereus_ping_status`) have no implementation at all.

## 10. Next eval sets worth building (real data)

1. **HYS14 clock (strongest).** Run `atlas_tasks.timing` on the real
   HYS12–HYS14 MHZ MiniSEED from EarthScope and compare its Δt track hour by
   hour with Maleen's `delta_t_hourly_clean.npy` and `trigger_periods.csv`
   from chronos. Agreement within 0.125 s is the bar.
2. **Gaps on real PREST/VEL3D days.** Truth comes from the COSZO
   `*variability.csv` columns (`n_gaps`, `true_missing`, `jitter_unstable`) for
   days already checked by hand.
3. **A-0-A at Axial.** Process the PI-portal `PI-A0ABPA301` record and compare
   the drift with the published A-0-A drift estimates for Axial (e.g. Sasagawa et al. 2016).
4. **dv/v at Axial.** Compare with a published Axial dv/v time series over a
   shared window.
5. **Human-graded answers.** Grade the judge calibration sheet, report κ, and
   grow the v1 reference answers by category.

## 11. Running and extending

```sh
python3.12 -m venv .venv && .venv/bin/pip install numpy scipy matplotlib pytest
cd src
../.venv/bin/python -m atlas_eval list
../.venv/bin/python -m atlas_eval build                     # regenerate synthetic datasets (deterministic)
../.venv/bin/python -m atlas_eval run --suites offline --out atlas_eval/results/<run>
../.venv/bin/python -m atlas_eval run --suites retrieval answers --out atlas_eval/results/<run>
../.venv/bin/python -m atlas_eval retry atlas_eval/results/<run> answers   # re-ask 503s, slower
../.venv/bin/python -m atlas_eval judge atlas_eval/results/<run>           # needs the claude CLI
../.venv/bin/python -m atlas_eval run --suites agent_llm --agent-model haiku --out atlas_eval/results/<run>
../.venv/bin/python -m atlas_eval report atlas_eval/results/<run>   # report.md + catalog.html
```

`catalog.html` is the place to review a run: open it in a browser to see every
task, its expected truth, what the system returned, how it scored, the figures,
and the environment the run executed in.

To add a case, append a line to the suite's dataset (or extend
`build_cases`), and bump the file to `_v2` if `v1` has been reported. To add a
suite, subclass `suites.base.Suite` with `run_case`, `score_case`, and
`summarize`, and register it in `suites/__init__.py`. Node is needed for the
suites that run the Worker's own JavaScript.
