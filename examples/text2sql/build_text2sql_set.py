"""Build the text2sql test set: the agent author's own 19 Spider questions + 21 random Spider dev questions.

    python3 build_text2sql_set.py <data dir> <text2sql-framework folder> [extra]

`extra` (default 0) adds that many more random Spider dev questions (seed 43, ids sp041...) after the
original 40, which keep their ids, so a larger held-out set can be built without touching recorded runs.

<data dir> must hold spider_db/<db_id>.sqlite for the 20 Spider dev databases and spider_dev.json
(the Spider dev questions: [{"db_id", "question", "query"}]). Writes <data dir>/spider_dev_merged.sqlite
(the author's "80-table" setup: on a table-name clash the first database wins and questions on the
losing database are left out), <data dir>/text2sql_tasks.json and <text2sql folder>/tasks.jsonl.
"""
import json, random, re, sqlite3, sys
from pathlib import Path

DATA = Path(sys.argv[1]); T2S = Path(sys.argv[2])
dev = json.loads((DATA / "spider_dev.json").read_text())
order = ["concert_singer", "pets_1", "car_1", "flight_2", "employee_hire_evaluation", "cre_Doc_Template_Mgt", "course_teach",
         "museum_visit", "wta_1", "battle_death", "student_transcripts_tracking", "tvshow", "poker_player", "voter_1",
         "world_1", "orchestra", "network_1", "dog_kennels", "singer", "real_estate_properties"]
merged = DATA / "spider_dev_merged.sqlite"
merged.unlink(missing_ok=True)
m = sqlite3.connect(merged)
owner, skipped_dbs = {}, set()
for db in order:
    src = DATA / "spider_db" / f"{db}.sqlite"
    m.execute(f"ATTACH DATABASE '{src}' AS s")
    for name, sql in m.execute("SELECT name, sql FROM s.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
        if name.lower() in owner:
            print(f"clash: {db}.{name} already from {owner[name.lower()]}; skipping questions on {db}")
            skipped_dbs.add(db); continue
        owner[name.lower()] = db
        m.execute(sql)
        m.execute(f'INSERT INTO main."{name}" SELECT * FROM s."{name}"')
    m.commit(); m.execute("DETACH DATABASE s")
print("tables in merged db:", m.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0])

md = (T2S / "examples" / "spider_80_table_run.md").read_text()
author_qs = re.findall(r"^## \d+\. (.+)$", md, re.M)
norm = lambda s: " ".join(s.lower().split())
by_q = {}
for r in dev:
    by_q.setdefault(norm(r["question"]), r)
tasks = []
for q in author_qs:
    r = by_q.get(norm(q))
    assert r, f"author question not in Spider dev: {q}"
    tasks.append({**r, "source": "author_benchmark"})
used = {norm(t["question"]) for t in tasks}
pool = [r for r in dev if norm(r["question"]) not in used and r["db_id"] not in skipped_dbs]
rng = random.Random(42)
for r in rng.sample(pool, 21):
    tasks.append({**r, "source": "random_dev_seed42"})
extra = int(sys.argv[3]) if len(sys.argv) > 3 else 0
if extra:
    used = {norm(t["question"]) for t in tasks}
    pool = [r for r in dev if norm(r["question"]) not in used and r["db_id"] not in skipped_dbs]
    for r in random.Random(43).sample(pool, extra):
        tasks.append({**r, "source": "random_dev_seed43_extra"})
for i, t in enumerate(tasks, 1):
    t["id"] = f"sp{i:02d}" if i <= 40 else f"sp{i:03d}"
(DATA / "text2sql_tasks.json").write_text(json.dumps(tasks, indent=1))
with (T2S / "tasks.jsonl").open("w") as f:
    for t in tasks:
        f.write(json.dumps({"id": t["id"], "input": t["question"], "expected": {"db_id": t["db_id"], "gold_sql": t["query"]}, "meta": {"source": t["source"]}}) + "\n")
print(len(tasks), "tasks;", sum(t["source"] == "author_benchmark" for t in tasks), "from the author's benchmark")
