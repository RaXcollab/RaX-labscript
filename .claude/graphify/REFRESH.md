# Graphify graph refresh recipe

Rebuilds `graphify-out/graph.json` (workspace knowledge graph) from scratch.
Built 2026-07-29 (commit 9333da6): 5090 nodes / 8176 edges / 371 communities, 31 cross-repo edges.
Provenance: audit + fix-pass reports in `.claude/session-scratch.md` (session 2026-07-29).

## Recipe

All from `C:\Users\radmo\labscript-suite`, in the **base** conda env (NEVER the labscript env):

```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate base

# 1. shim the .pyw (graphify's CODE_EXTENSIONS has no .pyw)
cp "GUIs/BigSkyControl/HugeSkyController.pyw" "GUIs/BigSkyControl/HugeSkyController_pyw_shim.py"

# 2. five forced per-directory extracts (per-dir is FORCED: parent .gitignore
#    excludes the backend repos, so a single-rooted extract is not available)
graphify extract userlib           --code-only --force
graphify extract blacs             --code-only --force
graphify extract labscript-devices --code-only --force
graphify extract labscript-utils   --code-only --force
graphify extract GUIs              --code-only --no-gitignore --force   # --no-gitignore ONLY here

# 3. merge (backup the unfiltered result)
graphify merge-graphs userlib/graphify-out/graph.json blacs/graphify-out/graph.json \
  labscript-devices/graphify-out/graph.json labscript-utils/graphify-out/graph.json \
  GUIs/graphify-out/graph.json --out graphify-out/graph.json
cp graphify-out/graph.json graphify-out/graph.unfiltered.json

# 4. post-merge fixes: filter legacy trees (Old Code/, *-zmq-v2, dead
#    labscript_devices/RemoteControl), rewrite shim path -> .pyw,
#    import-gated cross-repo stub fusion. Supports --dry-run.
python .claude/graphify/postmerge_fix.py

# 5. recluster, delete the shim
graphify cluster-only . --no-label
rm "GUIs/BigSkyControl/HugeSkyController_pyw_shim.py"

# 6. verify (13-check suite; all must pass)
python .claude/graphify/verify_fix.py
```

## Known quirks

- **"pre-#1504 node-ID scheme" warning on query/serve is a false positive** for any
  merged graph — `merge-graphs` prefixes IDs with `<repo>::` and the legacy-ID
  heuristic doesn't strip it. Cosmetic; ignore. IDs ARE path-qualified.
- **Invisible by design (AST ceiling):** ZMQ runtime couplings (GUI <-> BLACS device;
  use the External GUI Registry / `docs/external-guis-architecture.md` instead), and
  BLACS worker wiring via string paths (e.g. LaserLockTab creates RemoteControlWorker
  by string at `LaserLockDevice/blacs_tabs.py:351` — no edge exists; do NOT synthesize one).
- Stubs from pip-installed `labscript` core (Device, StaticAnalogQuantity, ...) can
  never resolve inside this workspace — expected, not a defect.
- `graphify query --help` is parsed as a query string, not help. Query output
  truncates against a token budget — watch for the "cut nodes" warning.
- `graph.html` skipped above 5000 nodes; raise `GRAPHIFY_VIZ_NODE_LIMIT` to force.
- ~22% of nodes are `file_type=rationale` (docstring prose, `rationale_for` edges
  only) — harmless inflation, kept deliberately.

## Graph vs digests vs smart-explore

- **Graph** (`graphify query "<q>"`) — you know the symbol and want its structural neighbourhood: callers, imports, subclasses, intra-repo blast radius.
- **Digests** (`.claude/agent-memory/codebase-digests/`) — you want intent, landmines, and line-numbered invariants for a subsystem. Read these first for "how does X work" / "what breaks if I change it".
- **smart-explore** (`smart_search` / `smart_outline`) — you don't know what the thing is called yet.

## When to refresh

- After the Z1–Z4 ZMQ cutover merges: `userlib/external_gui_lib/` gains real `.py`
  sources → first genuine GUI<->userlib structural bridge. Highest-value rebuild.
- After any large refactor that moves/renames modules across the five roots.
