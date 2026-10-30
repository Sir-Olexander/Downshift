# Proving the optimizer: the plan

Written 2026-10-29 on branch `prove-the-optimizer-plan`. Everything here rests on the evidence in
`docs/research/` (six research notes, two evidence notes, one diagnostic) and on the state of the code after
this branch's commits. Numbers are quoted with their sample sizes on purpose: most of them are small.

## 0. What "proven" has to mean

The open items from the last review, turned into claims a reader could check:

| # | Claim to establish | Status today |
|---|---|---|
| P1 | On at least one real agent, a Downshift rewrite beats the plain model swap by a margin the data can support, and keeps the expensive model's quality | Not shown. text2sql Super: rewrite = swap within noise. Nano: every rewrite was worse than the swap |
| P2 | Downshift's reported numbers are trustworthy: fresh runs land inside the stated interval | Not shown. One replay of 16 tasks per claim; 62.5% reported, 44% fresh |
| P3 | The result repeats on a second and third outside agent, through Downshift, not by hand | Not shown. text2sql only; tau2-bench ran outside Downshift |
| P4 | Connecting an agent is cheap | Partly. text2sql needed an adapter that reaches into its internals |
| P5 | The original demo results (LLM judge) hold against correct answers | Not checked |
| P6 | The optimizer's model knowledge is right (the thinking-off problem is one symptom) | Fixed in this branch for 10 models; the re-run has not happened |

## 1. What the evidence says

### 1.1 Our own data (text2sql, Nano, 16 held-out Spider tasks)

Details: `research/text2sql-failure-taxonomy.md`, `research/nano-text2sql-diagnostic.md`.

| harness | pass | what fails |
|---|---|---|
| Ultra, text2sql's own prompt (fresh, 2 trials) | 11/16, 12/16 | wrong results only, several on debatable Spider gold queries |
| Super, Downshift's rewrite (fresh, 2 trials) | 13/16, 12/16 | wrong results |
| Nano, plain swap, thinking on (fresh, 3 trials across two providers) | 7, 7, 8 of 16 | **7 of 9 failures are prose answers with no ```sql block; in 5-6 of them the prose contains the correct values** |
| Nano, plain swap, thinking off (1 trial) | 4/16 | more prose, more wrong SQL; tool calls still work |
| Nano, Downshift's first rewrite (thinking off, few-shot that wrote tool calls as text) | 2/16 | the model copied the text format and never ran a query |
| Nano, plain swap, thinking on, **plus one final-reply format rule** (hand-written diagnostic, 1 trial) | **14/16** | two semantic misses, the same tasks Ultra misses |

So the gap Downshift could not close is a container problem, not a reasoning problem, and the fix is a
two-sentence prompt rule that costs nothing. The optimizer did not find it for four reasons, each now
visible in the stored rounds:

1. The guidance told it thinking off makes "mechanical steps" cheap, so every Nano rewrite set
   `reasoning: off` and the failures changed character before the rewriter could see the real one.
2. The rewriter saw the extracted SQL (empty) of failed runs, not the model's final message (a prose table
   with the right numbers).
3. The objective adds up to 10 points for cost savings and the prompt says "prefer fewer, cheaper calls";
   on an 8-task sample one task is 12.5 points, so cost could outrank correctness.
4. Each candidate was judged on 8 tasks and the best of several candidates was reported from that: the
   "winner's curse" alone inflates the chosen candidate by about 13-15 points
   (`research/evaluation-methodology.md`).

Items 1 and 2 are fixed on this branch. Items 3 and 4 are Phase 0 and Phase 1 below.

### 1.2 What the research says (one line each; the notes have the sources)

- **Prompt-level fixes work for format, not for capability** (`research/beyond-prompt-rewriting.md`): the
  cheapest evidence-backed intervention is a repair turn checked against the agent's own output contract
  (+10-20 pp expected on Nano text2sql); best-of-n adds 0-4 pp on Spider and costs as much as plain Super;
  learned routers need thousands of labels; fine-tuning on Ultra traces is the largest reported gain
  (+9-20 pp) but Token Factory fine-tunes 49 models and no Nemotron.
- **Prompt-only optimization has never lifted a ~3B-active model to a frontier model in the literature**
  (`research/prompt-optimization-for-small-models.md`): GEPA's smallest Qwen3 models went flat or down;
  optimizers with stable gains used 111-500 validation items and thousands of rollouts (DSPy asks for
  300 examples, 80% of them for validation); bootstrapped few-shot from the big model's own successful
  traces is the best-supported lever for small models; long expert prompts transfer badly to them (a
  small model drops from 94% to 73% instruction following going from 10 to 50 rules); and a prompted 7B
  model reaches about 73% on Spider dev, so Nano's 56% points at format and serving, not SQL ability.
- **Prior migration work mostly reports nulls** (`research/outside-agents-and-testbeds.md`): an
  independent production study found neither manual rewrites, a vendor prompt optimizer nor DSPy beat
  the original prompt; vendor migration tools publish n = 5 or no held-out set. Nobody publishes the
  full combination Downshift attempts (tool-using agent, cheaper model, rewritten harness, correct
  answers, held-out split, plain swap shown, fresh re-check). Honest nulls are part of that niche.
- **Thinking off is a quality knob on Nano, not a breakage** (`research/nemotron-3-model-guides.md`): only
  about 10% of Nano's post-training data was non-reasoning; independent benchmarks fall sharply with it
  off; the "tool calls as text" failure came from Downshift's own few-shot. vLLM ignores `reasoning_effort`
  for Nemotron 3, so `low/medium/high` on Token Factory were silent no-ops; the real switches are the
  chat-template flags `low_effort` (Super) and `medium_effort` (Ultra).
- **16 tasks cannot support a 10-point claim at any number of trials**
  (`research/evaluation-methodology.md`): a pass rate on 16 tasks has a 95% interval of about ±22 pp; a 10
  pp paired difference at 80% power needs about 200-250 tasks × 1 trial or 90-140 × 3; add tasks before
  trials; use paired tests, Wilson intervals, a non-inferiority bar with an "inconclusive" verdict, and
  never report dev-set scores.
- **The judge has never been validated and the literature says judges are biased** (position, length,
  self-preference); 130-170 human-labelled outputs would settle it for the research agent.
- **Other families are usable as test beds** (`research/ollama-cloud-models.md`,
  `research/ollama-cloud-probe.md`): three cheap/expensive pairs (gpt-oss 120B/20B, GLM-5.3/Flash, DeepSeek
  V4 Pro/V4.1 Flash) plus Gemma 4 31B have papers, tool calling and verified thinking controls; Ollama
  Cloud supports no `tool_choice`, no `n`, no logprobs, and does not enforce structured outputs.
- Ollama Pro is documented as $20/month with $60 of included per-token usage and 3 concurrent requests
  (not uncapped); the Token Factory key has about $4.40 of its $15 left (RESULTS.md running total).

### 1.3 Verdict on the two suggestions in the brief

**"Fix the rewriter guidance about turning thinking off, then re-run Nano on text2sql."** Good, and done
in part: the guidance now says thinking stays on for tool loops, with the reasons. But the fix alone would
not have been enough: the rewriter also had to see the prose failures, stop being paid for cost on tiny
samples, and the adapter had to enforce its tool budget (one run reached 50 calls and 900k tokens). The
re-run should be a controlled experiment with the plain swap as control, not another 8-task optimization.
Phase 0 describes it; it is the first thing to run, after the user's go-ahead (CLAUDE.md).

**"Write the harnesses with each model's technical paper in mind."** Good, and the right version of it is
already in the repo: `server/app/optimizer/guidance.py` now carries notes for 10 models drawn from their
technical reports and model cards (thinking modes and their cost, sampling, token budgets, tool-call format,
known failure modes), with sources in `docs/research/`. Two refinements make it more than a prompt: the
switch behaviour was checked against the live endpoint with `python -m downshift.probe` and encoded in the
model table (so a harness can only ask a model for a thinking level that exists), and the rewriter should
get the *baseline* model's guide too, so it knows what it is moving away from. A live web lookup is not a
substitute: the keyless one returned Wikipedia pages about NVIDIA.

## 2. The plan

### Phase 0 (hours): let the optimizer find the fix, then check it

Done on this branch:

- Guidance rewritten from the technical reports; keyless lookup skipped (`guidance.py`).
- The rewriter sees the model's final message for the worst runs (`engine.py`, `rewrite.py`).
- Nemotron's thinking levels are real switches or rejected, never silent no-ops (`models.yaml`,
  `pricing.py`, `harness.py`).
- The text2sql adapter enforces `max_tool_calls` by withholding tools once the budget is spent.

Still to do, in order:

1. **Objective: correctness first, cost only as a tie-breaker.** In `metrics.objective`, apply the cost
   bonus only between candidates whose success rates are within one task of each other; in the rewrite
   prompt replace "prefer fewer, cheaper model calls" with "correctness first; cut cost only where the
   recorded runs show it is free". One hour, unit-tested.
2. **Bigger optimization sample.** Set `DOWNSHIFT_OPT_SAMPLE=20` (the text2sql optimization split has 24
   tasks) and `--rounds 3`. The round cost on Nano is about $0.03 at Token Factory prices.
3. **Re-run the Nano optimization on text2sql, on Ollama**, after asking the user (CLAUDE.md):

   ```bash
   DOWNSHIFT_PROVIDER=ollama DOWNSHIFT_OPT_SAMPLE=20 uv run python -m app.cli optimize \
       --project text2sql --targets nano --rounds 3 --source live
   ```

   Run it three times with different `--seed` values: the rewriter is stochastic, and "how often does it
   find a final-reply rule" is the result, not one lucky run. About $0.40 per run at Token Factory list
   prices (Ultra rewrites dominate), roughly 15 minutes each.
4. **Fresh-run check** of every recommended harness, two trials, on the 16 held-out tasks, with the plain
   swap and the Ultra baseline as controls (`verify_downshift.py export/report`, then
   `downshift.runner record` per arm). Report pass counts, the failure classes
   (`text2sql-failure-taxonomy.md` rule), cost per task and output tokens.
5. **What counts.** The optimizer passes Phase 0 if, in at least 2 of 3 runs, its Nano harness keeps
   thinking on, contains an explicit final-reply rule, and scores at least 12/16 fresh where the swap
   scores about 8/16. If it instead proposes other changes and stays at the swap's level, that is the
   finding: prompt rewriting through this loop cannot reach what a two-sentence rule reaches, and Phase 3's
   repair turn moves up the list.

**Outcome (2026-10-29, `research/phase0-results.md`):** all three runs found the final-reply rule and kept
thinking on; one harness of three scored 14 and 12 of 16 fresh (Ultra 11-12, swap 7-8) at about a tenth of
Ultra's cost; the other two scored 8-11 fresh, and one of them had been reported at 14/16 from a single
replay. The bar (2 of 3 at 12 or more) was not met: the optimizer finds the idea, not reliably the
minimal harness, and single replays of 16 tasks cannot tell its candidates apart. Phase 1 is next.

Expected headline if it works: "Nano reaches Ultra's quality on this agent at about one eighth of the
cost; the plain swap does not". Not "Nano is free": Super already matches Ultra with no changes, and the
Nano harness's remaining failures are the semantic ones Ultra also makes.

### Phase 1 (days): numbers a reader can trust

**Outcome (2026-10-30, `research/phase1-results.md`):** done: 240 tasks, trials, paired intervals, the
non-inferiority verdict, racing and `verify` are in the engine. Super: non-inferior, rewrite = swap. Nano:
the optimizer's own run kept the swap (inconclusive at −9.7 pp); the Phase 0 harness, on 80 untouched tasks,
is non-inferior to Ultra and beats the swap by about 12 points on both providers (bar item 1 met for that
harness, not yet for the optimizer as a procedure). Trials matter little here (intraclass correlation
0.81-0.85); tasks do.

1. **Grow the text2sql task set to 240.** `examples/text2sql/build_text2sql_set.py` already samples Spider
   dev; all 1034 dev questions have their database locally. Keep the 40 existing tasks as they are and add
   200 stratified by database (seed 42). Record the Ultra baseline on the new tasks on Ollama (about $2.60
   at Token Factory list prices, 40 minutes at concurrency 3). Clean the four known flawed gold queries
   or keep a "clean subset" flag so both numbers can be shown.
2. **Pilot the variance.** Baseline and plain Nano swap, fresh, 30 tasks × 3 trials each; compute the
   within-task and between-task variance and the replay-vs-fresh gap on the same tasks; size the held-out
   set from the Miller formula with those estimates (`evaluation-methodology.md` §2 and §7).
3. **Evaluation protocol in the engine, not in a side script:**
   - `K` trials per task on the held-out set (`--trials`, default 3 when tasks are scarce, 1 when they are
     plentiful); report pass^1 and pass^K.
   - Paired per-task differences against the baseline and against the plain swap; Wilson intervals for
     rates; cluster-bootstrap intervals for paired deltas and for cost per run.
   - Replace `meets_bar` (one-run drop allowed) with a non-inferiority test: non-inferior if the lower bound
     of the 90% interval of the paired delta is above −M (M = 10 pp default), with a third verdict,
     **inconclusive**, when the interval crosses −M.
   - "Rewrite beats swap" as a pre-registered paired superiority test; keep the swap unless the rewrite's
     interval excludes zero; Holm correction across Super, Nano and the mix.
   - Candidate selection by racing: every candidate on 20 tasks, the top two plus the swap on 30 more × 2
     trials; dev scores are never shown as results.
   - Every results row prints n, K, fresh or replay, the interval, the verdict, the smallest detectable
     gap, and how many candidates were tried on how many dev tasks. The README report and the web table get
     the same columns.
4. **Fresh-run audit as a command.** `app.cli verify <optimization id>`: runs the chosen harness, the swap
   and the baseline fresh (2 trials) on the held-out tasks and prints replay vs fresh side by side. This is
   `demo_agents_2/_eval/verify_downshift.py` promoted into the product; it must live in the tracked tree.
5. **Re-run text2sql at scale**: Super, Nano and the mix on the 240-task set, 100 held-out tasks × 3
   trials. At Token Factory list prices about $6 (Ultra fresh trials dominate); on Ollama it counts against
   the $60 allowance.

### Phase 2 (days): two more outside agents, and a cheaper way to connect one

1. **A recording proxy instead of a per-agent adapter.** `python -m downshift.proxy` serves an
   OpenAI-compatible endpoint that forwards to the provider, records every call as a run (task id from a
   header or a per-run session), and applies the harness on the way through (replace the agent's system
   prompt when it matches the recorded original, set model and sampling per step). Any agent with a
   configurable base URL then needs no adapter code; the adapter shrinks to a task list, a grader and a
   one-line driver. tau2-bench, BFCL and mini-SWE-agent already point at an endpoint through one setting.
   What the proxy must handle: a task id per request (header or per-task endpoint path), separate
   endpoints for the agent and a benchmark's user simulator, live replays only (it cannot serve recorded
   tool results), and a step that reads the benchmark's own scores back into `tasks.jsonl`.
2. **tau2-bench telecom, then retail, through Downshift** (`research/outside-agents-and-testbeds.md`).
   Telecom first: all 40 of its test tasks are graded without any LLM judge, and NVIDIA's own model cards
   put Nano 22 points below Super there (42.2 vs 64.4), which is exactly the "swap fails" setting the
   rewriter needs. Driver: run tau2 per task through the proxy and take tau2's own reward as the grade;
   replays run live (state-changing tools; simulated user on Super with thinking off, as before). Smoke-test
   3 tasks first (about $0.15; telecom conversation length is unmeasured). Make **Super the baseline** for
   this agent: Ultra scored below Super and Nano on retail at 5-7× the cost, and Downshift's premise is
   "cheaper than what you run today". Super → Nano, 40 tasks × 3 trials, about $5 at Token Factory prices.
   Retail second, with its 11 judge-graded tasks left out: the one-trial result (Nano 70% vs Ultra 45% on
   20 tasks) contradicts NVIDIA's own 56.9 for Nano and needs 3 trials before anyone quotes it.
3. **BFCL v4 multi-turn, then BIRD mini-dev.** BFCL v4's multi-turn categories check final state and call
   paths deterministically, need no user simulator, point at a remote endpoint through one environment
   variable, and have a published 30B → 235B gap of 15-21 points; its single-turn categories (no gap) are
   the "just swap" control (about $1.20 with Super as baseline). BIRD mini-dev (500 SQLite tasks, execution
   accuracy, Llama 3 8B → 70B gap of 16 points) reuses the text2sql adapter almost unchanged and is newer
   than Spider dev, which has been public since 2018 and is probably in training data; it checks whether the
   Spider result generalises (about $1.30 with Super as baseline). Avoid judge-graded or VM-heavy suites
   (StableToolBench, MINT, TheAgentCompany, OSWorld) and the saturated ones (GSM8K, IFEval, HumanEval).
4. **The decision test.** For each agent, Downshift's recommendation (which option, or "swap only") must
   agree with the fresh-run audit. A correct "just swap" is a pass for the product even though it proves
   nothing about the rewriter; the rewriter claim is only made where the swap fails.

### Phase 3 (a week or more): optimizer and SDK changes the evidence supports

1. **Runtime knobs in `run.chat`, declared in harness.yaml, so the optimizer can switch them on:**
   - `contract` check + **repair turn**: if the final reply breaks the agent's own output contract (a regex
     or a small callable in the adapter), send one short re-ask. Report the trigger rate and count it in
     the cost. This is the diagnostic's format rule applied at runtime for any model.
   - **Text tool-call recovery**: content that holds `<tool_call><function=...>` or JSON matching a tool's
     schema becomes a real tool call (documented Nemotron parser gap: 27 in 1000 responses in one serving
     stack; seen once in our thinking-off runs).
   - Forced named `tool_choice` on Token Factory for steps that must end in a tool call (documented there;
     unsupported on Ollama Cloud).
   - A **deterministic cascade** (escalate the task to the next model when the contract still fails after
     the repair turn), only if the escalation rate measured in Phase 1 is below about 15%; above that it
     saves less than plain Super.
   - Not: JSON-schema constraints on reasoning or tool-loop steps (−26 points on reasoning tasks in the
     literature, unenforced on Ollama), best-of-n as the main fix, learned routers, a generic LLM verify
     step without an execution signal.
2. **Optimizer loop, reshaped by the literature** (`research/prompt-optimization-for-small-models.md`):
   - more than one candidate per round, kept as a Pareto set over tasks (a candidate survives while it is
     best on at least one task) rather than one best; accepted only when a paired test on the dev set
     shows it beats the plain swap;
   - small edits to one part of the harness at a time instead of regenerating the whole file: the text
     tool-call few-shot and the Postgres schema queries both came from whole-harness rewrites;
   - per-failure diagnostics in the feedback (failure class, expected vs actual result, the final message,
     the failing step) rather than three worst examples;
   - few-shot taken from the baseline's own successful recorded runs on the optimization split, passed as
     real message turns with the real tool calls and results (an SDK change: `few_shot` items may be
     trajectories, not only text pairs). This is the best-supported lever for small models in the
     literature, and it cannot teach a text tool-call format;
   - sampling settings taken from the model guide, not chosen by the rewriter; rewrites kept short, since
     instruction following falls steeply as rules pile up;
   - the per-step mix target and the research runtime's step changes stay.
3. **Model guides as a maintained artifact.** `MODEL_NOTES` plus the probe-verified switch table are the
   "technical paper" idea; keep each guide to the facts a rewriter can act on, record the source, re-probe
   when a provider changes, and give the rewriter both the target's and the baseline's guide.
4. **Other families.** Generalise `TARGETS` from fixed Nemotron tiers to family pairs: gpt-oss 120B → 20B,
   GLM-5.3 → GLM-5.3 Flash, DeepSeek V4 Pro → V4.1 Flash, with Gemma 4 31B as an extra small target. Run
   text2sql through each pair (baseline recorded on the big model, swap and rewrite on the small one, same
   protocol). This answers "does Downshift's rewrite add value beyond Nemotron" either way, and it keeps
   Nemotron as the core: the product's recommendation path and the hackathon story stay on Token Factory.
5. **Judge validation for the demo agent** (`evaluation-methodology.md` §7e): reference answers and 2-5
   key facts for the 42 questions; label about 130-170 existing outputs; judge both orders; report position
   consistency, agreement and kappa, false-pass and false-fail rates; re-judge with a non-Nemotron judge
   (gpt-oss 120B or GLM-5.3, now in the table) for self-preference; length bias by regression. Acceptance
   bar: position consistency ≥ 80%, human agreement ≥ 75%. If it fails, grade the demo agent against the key
   facts (ground truth) and retire the pairwise judge from the headline numbers.

## 3. What this plan does not try, and why

- **Fine-tuning Nano on Ultra traces.** Largest reported gains in the literature, but Token Factory does
  not fine-tune Nemotron, 500-2000 traces would cost about the whole remaining Token Factory budget, and the
  product promise is "a harness change in a PR", not a new checkpoint. Revisit if Token Factory adds
  Nemotron fine-tuning; the closest option today is Qwen3-30B-A3B with LoRA.
- **Tuning tasks, prompts or graders to make results look better** (CLAUDE.md). The format rule in the
  diagnostic is reported as a ceiling found by hand; the claim is only made when the optimizer finds an
  equivalent on the optimization split and it holds on a held-out split.
- **Claiming anything from 16 tasks.** Phase 1 comes before any public number.
- **Treating Spider dev as the only test.** It is probably in training data; the Phase 2 test beds are
  newer or state-based, and the plan reports all of them.

## 4. Budget and order

Costs at Token Factory list prices (what Downshift reports), whichever provider runs the calls. Bulk runs go
through Ollama (the user's Pro subscription; Ollama's page says $60 of usage is included per month, so
check the account's usage page), and the remaining Token Factory budget (about $4.40) is kept for the final
verification runs that the hackathon story needs on Token Factory.

| step | runs | estimated cost | wall clock at concurrency 3 |
|---|---|---|---|
| Phase 0: 3 Nano optimizations (20-task sample, 3 rounds) | ~250 Nano replays + 9 Ultra rewrites | ~$1.20 | ~45 min |
| Phase 0: fresh check, 3 arms × 2 trials × 16 tasks | 96 | ~$0.50 (Ultra arm $0.37) | ~20 min |
| Phase 1: 200 new baseline runs on Ultra | 200 | ~$2.60 | ~40 min |
| Phase 1: variance pilot, 2 systems × 30 × 3 | 180 | ~$1.20 | ~30 min |
| Phase 1: held-out 100 × 3 trials × (baseline, swap, rewrite) | 900 | ~$6 | ~3 h |
| Phase 2: tau2 Super → Nano, 40 × 3, two arms plus swap | 360 | ~$4.50 | ~4 h |
| Phase 3: one family pair on text2sql, same protocol | ~900 | $2-15 depending on the pair | ~3 h |

If the 30 October hackathon deadline still applies, only Phase 0 and the documentation fit before it; the
README already states what is and is not shown.

## 5. The bar for "proven"

1. On text2sql, the Nano harness that Downshift finds on its own is non-inferior to Ultra (M = 10 pp) on at
   least 100 held-out tasks × 3 trials, beats the plain Nano swap with a paired interval excluding zero, and
   costs at most a fifth of Ultra per task.
2. The fresh-run audit lands inside the interval of the replay-based claim.
3. The same pipeline, unchanged, gives a recommendation on tau2-bench and on a third agent that the audit
   confirms, including when the recommendation is "swap only".
4. One non-Nemotron family pair is reported under the same protocol, whichever way it comes out.
5. The demo agent's judge passes the validation bar or is replaced by ground-truth grading.

Until 1 and 2 hold, the honest public statement stays the one in the README: Downshift's decisions held on
one outside agent, its rewrites have not beaten a plain model swap, and the numbers are single replays of 16
tasks.
