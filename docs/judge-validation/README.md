# Validating the LLM judge on the research agent

The demo results in the README (the research agent, 42 questions) rest on a Nemotron 3 Ultra judge that
compares each candidate answer with the Ultra baseline answer. It has never been checked against people.
This folder is the material for that check (protocol: `docs/research/evaluation-methodology.md`, section 7e).

## Files

- `labels.csv`: 108 answers from optimization `opt_c5bcd27101b5` (the baseline answer for every question that has
  replays, plus every Super, Nano and per-step-mix replay on the held-out and optimization splits), in random
  order and without model labels. Fill in the three yes/no columns for each row:
  - **correct**: every fact, date and number in the answer is right (check against the cited sources or a
    reliable reference);
  - **complete**: it answers every part of the question;
  - **unsupported claim**: it states something its cited sources do not support.
- `key.json`: which task and which option each item came from. Do not open it while labelling.

About 60-100 labelled items estimate the judge's agreement with people to within about ±10 points; Cohen's
kappa to ±0.1 needs about 250.

## Automated first pass (no people needed)

`uv run --directory server python -m app.judge_audit audit opt_c5bcd27101b5 --judges nemotron-3-ultra,glm-5.3`
judges every held-out pair in both orders with the Ultra judge and with GLM-5.3 (another model family). Results
are in `docs/research/judge-audit.md`. That checks position bias and self-preference, not correctness: only the
human labels can say whether the judge is right.

## Acceptance bar (team choice)

Position consistency of at least 80%, agreement with the human labels of at least 75% (lower interval bound at
least 65%), and no clear preference for the Ultra baseline beyond what the human labels show. If the judge fails,
grade the research agent against key facts written per question (ground truth) instead of the pairwise judge.
