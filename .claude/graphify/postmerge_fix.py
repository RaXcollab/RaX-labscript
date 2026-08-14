"""Post-merge fixes for the labscript-suite graphify graph.

Run in the BASE conda env, from the workspace root, right after `graphify merge-graphs`
and BEFORE `graphify cluster-only . --no-label`.

Three phases:
  1. drop legacy/duplicate trees (Old Code, *-zmq-v2, dead labscript_devices/RemoteControl)
  2. rewrite the HugeSkyController_pyw_shim.py paths back to HugeSkyController.pyw
     (graphify's CODE_EXTENSIONS has no .pyw, so the real file is extracted via a shim copy)
  3. fuse cross-repo stubs into their real definition, but ONLY when an actual
     `from <module> import <Label>` in the referencing file names the module that
     defines the real node. Bare label matching is what fabricates edges.

Usage:  python postmerge_fix.py [--dry-run] [--graph PATH]
"""

import argparse
import ast
import collections
import json
import sys
from pathlib import Path

WORKSPACE = Path(r"C:\Users\radmo\labscript-suite")
REPO_ROOTS = {
    "userlib": WORKSPACE / "userlib",
    "blacs": WORKSPACE / "blacs",
    "labscript-devices": WORKSPACE / "labscript-devices",
    "labscript-utils": WORKSPACE / "labscript-utils",
    "GUIs": WORKSPACE / "GUIs",
}

SHIM_REL = "BigSkyControl/HugeSkyController_pyw_shim.py"
REAL_REL = "BigSkyControl/HugeSkyController.pyw"
SHIM_ID_FRAGMENT = "hugeskycontroller_pyw_shim"
REAL_ID_FRAGMENT = "hugeskycontroller"


def is_legacy(source_file: str, repo: str) -> bool:
    """True for nodes/edges belonging to a legacy or duplicated tree."""
    if not source_file:
        return False
    sf = source_file.replace("\\", "/")
    if "Old Code" in sf:
        return True
    if "-zmq-v2" in sf:
        return True
    # ponytail: rastering-* is the only worktree naming convention under GUIs/ today;
    # add prefixes here if another GUI grows sibling worktrees.
    if repo == "GUIs" and sf.startswith("rastering-"):
        return True
    if repo == "labscript-devices" and sf.startswith("labscript_devices/RemoteControl/"):
        return True
    return False


def phase1_filter(nodes, edges, report):
    drop_ids = {n["id"] for n in nodes if is_legacy(n.get("source_file") or "", n.get("repo") or "")}
    reasons = collections.Counter()
    for n in nodes:
        sf = (n.get("source_file") or "").replace("\\", "/")
        if n["id"] not in drop_ids:
            continue
        if "Old Code" in sf:
            reasons["Old Code"] += 1
        elif "-zmq-v2" in sf:
            reasons["-zmq-v2"] += 1
        elif sf.startswith("rastering-"):
            reasons["rastering-* worktree"] += 1
        else:
            reasons["dead labscript_devices/RemoteControl"] += 1

    nodes = [n for n in nodes if n["id"] not in drop_ids]
    kept_edges = []
    dropped_edges = 0
    for e in edges:
        if e["source"] in drop_ids or e["target"] in drop_ids:
            dropped_edges += 1
            continue
        # an edge recorded inside a legacy file is legacy even if both endpoints survive
        if is_legacy(e.get("source_file") or "", ""):
            dropped_edges += 1
            continue
        kept_edges.append(e)

    report["phase1_nodes_dropped"] = dict(reasons)
    report["phase1_edges_dropped"] = dropped_edges
    return nodes, kept_edges


def phase2_pyw(nodes, edges, report):
    """Rewrite shim paths/ids back to the real .pyw file."""
    touched = 0
    for n in nodes:
        hit = False
        sf = (n.get("source_file") or "").replace("\\", "/")
        if sf == SHIM_REL:
            n["source_file"] = REAL_REL
            hit = True
        for key in ("id", "local_id"):
            if SHIM_ID_FRAGMENT in (n.get(key) or ""):
                n[key] = n[key].replace(SHIM_ID_FRAGMENT, REAL_ID_FRAGMENT)
                hit = True
        for key in ("label", "norm_label"):
            v = n.get(key) or ""
            if "HugeSkyController_pyw_shim.py" in v:
                n[key] = v.replace("HugeSkyController_pyw_shim.py", "HugeSkyController.pyw")
                hit = True
            elif "hugeskycontroller_pyw_shim.py" in v:
                n[key] = v.replace("hugeskycontroller_pyw_shim.py", "hugeskycontroller.pyw")
                hit = True
        if hit:
            touched += 1

    for e in edges:
        if (e.get("source_file") or "").replace("\\", "/") == SHIM_REL:
            e["source_file"] = REAL_REL
        for key in ("source", "target"):
            if SHIM_ID_FRAGMENT in e[key]:
                e[key] = e[key].replace(SHIM_ID_FRAGMENT, REAL_ID_FRAGMENT)

    report["phase2_nodes_rewritten"] = touched
    return nodes, edges


_import_cache: dict[Path, dict[str, set[str]]] = {}


def imported_names(path: Path) -> dict[str, set[str]]:
    """{imported_name: {module_dotted_path, ...}} for absolute `from X import Y` only.

    Relative imports (level > 0) are intra-repo by construction and can never
    justify a cross-repo fusion, so they are skipped.
    """
    if path in _import_cache:
        return _import_cache[path]
    out: dict[str, set[str]] = collections.defaultdict(set)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except (OSError, SyntaxError, ValueError):
        _import_cache[path] = out
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for alias in node.names:
                out[alias.name].add(node.module)
    _import_cache[path] = dict(out)
    return _import_cache[path]


def module_matches(module: str, real_source_file: str) -> bool:
    """True when a dotted module path designates the file that holds the real node."""
    mod_path = module.replace(".", "/")
    real = (real_source_file or "").replace("\\", "/")
    if not real:
        return False
    stem = real.rsplit(".", 1)[0]  # strip extension
    return stem == mod_path or stem.endswith("/" + mod_path)


def phase3_stubs(nodes, edges, report):
    by_id = {n["id"]: n for n in nodes}
    stubs = {n["id"]: n for n in nodes if not (n.get("source_file") or "")}

    # candidate real definitions: non-stub nodes, indexed by exact label
    real_by_label = collections.defaultdict(list)
    for n in nodes:
        if n.get("source_file") and n.get("label"):
            real_by_label[n["label"]].append(n)

    created = []          # justified cross-repo edges
    rewired_per_stub = collections.Counter()

    for e in edges:
        for endpoint in ("source", "target"):
            stub = stubs.get(e[endpoint])
            if stub is None:
                continue
            other = by_id.get(e["source" if endpoint == "target" else "target"])
            if other is None:
                continue
            ref_rel = e.get("source_file") or (other.get("source_file") or "")
            if not ref_rel:
                continue
            root = REPO_ROOTS.get(other.get("repo") or stub.get("repo") or "")
            if root is None:
                continue
            ref_path = root / ref_rel.replace("\\", "/")
            if not ref_path.is_file():
                continue
            modules = imported_names(ref_path).get(stub["label"]) or set()
            if not modules:
                continue
            target_real = None
            justifying = None
            for cand in real_by_label.get(stub["label"], []):
                if cand.get("repo") == stub.get("repo"):
                    continue  # cross-repo only; intra-repo is the extractor's job
                for mod in modules:
                    if module_matches(mod, cand.get("source_file") or ""):
                        target_real, justifying = cand, mod
                        break
                if target_real:
                    break
            if not target_real:
                continue
            created.append({
                "stub": stub["id"],
                "label": stub["label"],
                "relation": e["relation"],
                "referencing_file": f"{other.get('repo')}/{ref_rel}",
                "import": f"from {justifying} import {stub['label']}",
                "real_node": target_real["id"],
                "real_source_file": f"{target_real.get('repo')}/{target_real.get('source_file')}",
            })
            e[endpoint] = target_real["id"]
            rewired_per_stub[stub["id"]] += 1

    # a stub with no surviving edge is noise; drop it
    still_used = {e["source"] for e in edges} | {e["target"] for e in edges}
    orphaned = [sid for sid in rewired_per_stub if sid not in still_used]
    nodes = [n for n in nodes if n["id"] not in set(orphaned)]

    report["phase3_edges_rewired"] = len(created)
    report["phase3_stubs_touched"] = len(rewired_per_stub)
    report["phase3_stubs_fully_absorbed"] = len(orphaned)
    report["phase3_detail"] = created
    return nodes, edges


def prune_orphan_stubs(nodes, edges, report):
    """Drop stub nodes left with zero edges after phase 1 (their referencing tree is gone)."""
    used = {e["source"] for e in edges} | {e["target"] for e in edges}
    before = len(nodes)
    nodes = [n for n in nodes if n.get("source_file") or n["id"] in used]
    report["orphan_stubs_pruned"] = before - len(nodes)
    return nodes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--graph", default=str(WORKSPACE / "graphify-out" / "graph.json"))
    args = ap.parse_args()

    gp = Path(args.graph)
    g = json.loads(gp.read_text(encoding="utf-8"))
    nodes, edges = g["nodes"], g["links"]
    report = {"before": {"nodes": len(nodes), "edges": len(edges)}}

    nodes, edges = phase1_filter(nodes, edges, report)
    nodes, edges = phase2_pyw(nodes, edges, report)
    nodes, edges = phase3_stubs(nodes, edges, report)
    nodes = prune_orphan_stubs(nodes, edges, report)

    report["after"] = {"nodes": len(nodes), "edges": len(edges)}
    g["nodes"], g["links"] = nodes, edges

    detail = report.pop("phase3_detail")
    print(json.dumps(report, indent=2))
    print(f"\n--- {len(detail)} justified cross-repo edges ---")
    for d in detail:
        print(f"  {d['relation']:<12} {d['referencing_file']}  ->  {d['real_source_file']}")
        print(f"               justified by: {d['import']}")

    if args.dry_run:
        print("\n[dry-run] graph.json NOT written")
        return
    gp.write_text(json.dumps(g, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {gp}")


if __name__ == "__main__":
    main()
