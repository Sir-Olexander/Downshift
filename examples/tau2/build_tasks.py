"""Write tasks.jsonl for one tau2 domain split: python3 build_tasks.py <tau2-bench folder> [domain] [split]"""
import json, sys
from pathlib import Path

root = Path(sys.argv[1]); domain = sys.argv[2] if len(sys.argv) > 2 else "telecom"; split = sys.argv[3] if len(sys.argv) > 3 else "test"
ids = json.loads((root / "data" / "tau2" / "domains" / domain / "split_tasks.json").read_text())[split]
with (root / "tasks.jsonl").open("w") as f:
    for i, t in enumerate(ids, 1):
        f.write(json.dumps({"id": f"{domain[:2]}{i:02d}", "input": t, "expected": {"reward": 1.0}, "meta": {"tau2_id": t, "domain": domain, "split": split}}) + "\n")
print(len(ids), "tasks written")
