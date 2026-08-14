"""Verification suite for the rebuilt labscript-suite graphify graph."""
import collections
import json
from pathlib import Path

G = Path(r"C:\Users\radmo\labscript-suite\graphify-out\graph.json")
g = json.loads(G.read_text(encoding="utf-8"))
nodes, edges = g["nodes"], g["links"]
by_id = {n["id"]: n for n in nodes}
ok = []


def check(name, passed, evidence):
    ok.append(passed)
    print(f"[{'PASS' if passed else 'FAIL'}] {name}\n       {evidence}")


print(f"TOTALS: {len(nodes)} nodes, {len(edges)} edges, "
      f"{len({n.get('community') for n in nodes})} communities\n")

# 1 - legacy trees gone
bad = [n["source_file"] for n in nodes
       if any(p in (n.get("source_file") or "") for p in ("Old Code", "-zmq-v2"))
       or (n.get("repo") == "labscript-devices"
           and (n.get("source_file") or "").startswith("labscript_devices/RemoteControl/"))]
check("no Old Code / -zmq-v2 / dead-RemoteControl nodes", not bad,
      f"{len(bad)} matching nodes" + (f" e.g. {bad[:3]}" if bad else ""))

# 1b - sibling worktrees of GUIs/rastering gone (duplicate code trees)
wt = [n["source_file"] for n in nodes
      if n.get("repo") == "GUIs" and (n.get("source_file") or "").startswith("rastering-")]
check("no GUIs/rastering-* worktree nodes", not wt,
      f"{len(wt)} matching nodes" + (f" e.g. {wt[:3]}" if wt else ""))

# 2 - no INFERRED edges across the former duplicate-tree boundary
cross = [e for e in edges
         if any(p in (by_id.get(e[k], {}).get("source_file") or "")
                for k in ("source", "target") for p in ("-zmq-v2",))]
check("no edges touching a -zmq-v2 tree", not cross, f"{len(cross)} such edges")

# 3 - RemoteControl live tree
rcw = [n for n in nodes if n.get("label") == "RemoteControlWorker"]
check("RemoteControlWorker resolves to the LIVE userlib tree",
      len(rcw) == 1 and rcw[0]["source_file"].startswith("user_devices/RemoteControl/"),
      "; ".join(f"{n['repo']}/{n['source_file']}" for n in rcw) or "NOT FOUND")

# live subclasses of the userlib RemoteControl base classes
base_ids = {n["id"]: n["label"] for n in nodes
            if n.get("repo") == "userlib"
            and (n.get("source_file") or "").startswith("user_devices/RemoteControl/")
            and n.get("source_location", "") != "L1"}
subs = collections.defaultdict(list)
for e in edges:
    if e["relation"] == "inherits" and e["target"] in base_ids:
        src = by_id.get(e["source"])
        if src:
            subs[base_ids[e["target"]]].append(f"{src['label']} ({src['source_file']})")
# LaserLockDevice has no blacs_workers.py — LaserLockTab.initialise_workers names the
# base RemoteControlWorker by string path, so only 2 worker SUBCLASSES exist on disk.
worker_subs = subs.get("RemoteControlWorker", [])
check("live worker subclasses inherit RemoteControlWorker (2 on disk)", len(worker_subs) >= 2,
      "; ".join(sorted(worker_subs)) or "none")
tab_subs = subs.get("RemoteControlTab", [])
check("live subclasses inherit RemoteControlTab", len(tab_subs) >= 3,
      "; ".join(sorted(tab_subs)) or "none")

# 4 - .pyw nodes present, no shim residue
pyw = [n for n in nodes if (n.get("source_file") or "").endswith("HugeSkyController.pyw")]
want = {"BigSkyZmqServer", "MyTableWidget", "HomeTab"}
have = {n["label"] for n in pyw}
check("BigSkyZmqServer / MyTableWidget / HomeTab exist under HugeSkyController.pyw",
      want <= have, f"{len(pyw)} nodes from that file; found {sorted(want & have)}")
shim = [n["id"] for n in nodes if "pyw_shim" in json.dumps(n)] + \
       [e for e in edges if "pyw_shim" in json.dumps(e)]
check("no _pyw_shim residue anywhere in the graph", not shim, f"{len(shim)} residual references")

# 5 - cross-repo edges
xr = [e for e in edges
      if by_id.get(e["source"], {}).get("repo") and by_id.get(e["target"], {}).get("repo")
      and by_id[e["source"]]["repo"] != by_id[e["target"]]["repo"]]
pairs = collections.Counter(
    "{}->{}".format(by_id[e["source"]]["repo"], by_id[e["target"]]["repo"]) for e in xr)
check("cross-repo edge count > 0", len(xr) > 0,
      f"{len(xr)} cross-repo edges; pairs: {dict(pairs)}")

# 6 - intra-repo sanity spot checks
def has_inherit(child_label, parent_label):
    for e in edges:
        if e["relation"] != "inherits":
            continue
        s, t = by_id.get(e["source"]), by_id.get(e["target"])
        if s and t and s["label"] == child_label and t["label"] == parent_label:
            return f"{s['repo']}/{s['source_file']} -> {t['repo']}/{t['source_file']}"
    return None


for child, parent in (("BigSkyTab", "RemoteControlTab"), ("RasteringDevice", "RemoteControl")):
    ev = has_inherit(child, parent)
    check(f"{child} inherits {parent}", bool(ev), ev or "edge missing")

# 7 - self-loops / duplicate edges introduced by the stub fusion
loops = [e for e in edges if e["source"] == e["target"]]
dupes = [k for k, c in collections.Counter(
    (e["source"], e["target"], e["relation"]) for e in edges).items() if c > 1]
check("no self-loops", not loops, f"{len(loops)} self-loops")
check("no duplicate (source,target,relation) edges", not dupes, f"{len(dupes)} duplicates")

# 8 - dangling endpoints
dangling = [e for e in edges if e["source"] not in by_id or e["target"] not in by_id]
check("no dangling edge endpoints", not dangling, f"{len(dangling)} dangling")

print(f"\n{sum(ok)}/{len(ok)} checks passed")
