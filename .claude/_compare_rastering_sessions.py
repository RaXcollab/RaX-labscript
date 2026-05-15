import json, os, re, sys
DIR = r"C:/Users/radmo/.claude/projects/c--Users-radmo-labscript-suite"
SESSIONS = {
    "A_this(24807038)": "24807038-e2cf-41a1-9e78-3bfdbaec1421.jsonl",
    "B_other(4e7fb19c)": "4e7fb19c-1d3d-41a3-8195-4bc3171453bf.jsonl",
}

def load(path):
    rows = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows

def role_text(rec):
    msg = rec.get("message") or {}
    if not isinstance(msg, dict): return None, None
    role = msg.get("role")
    content = msg.get("content")
    if isinstance(content, str):
        return role, content
    if isinstance(content, list):
        parts = []
        for c in content:
            if not isinstance(c, dict): continue
            t = c.get("type")
            if t == "text":
                parts.append(c.get("text",""))
            elif t == "tool_use":
                tname = c.get("name","")
                inp = c.get("input",{}) or {}
                if tname in ("Edit","Write","Read","NotebookEdit"):
                    parts.append(f"<TOOL {tname} {inp.get('file_path','?')}>")
                elif tname == "Bash":
                    parts.append(f"<BASH {(inp.get('command','') or '')[:100]}>")
                elif tname == "TodoWrite":
                    todos = inp.get("todos",[]) or []
                    parts.append("<TODOS n=" + str(len(todos)) + " :: " + " | ".join(f"[{t.get('status','?')}] {t.get('content','')[:60]}" for t in todos[:12]) + ">")
                elif tname == "Task":
                    parts.append(f"<AGENT {inp.get('subagent_type','fork')} :: {(inp.get('description','') or '')[:80]}>")
                elif tname == "Skill":
                    parts.append(f"<SKILL {inp.get('skill','')}>")
                else:
                    parts.append(f"<TOOL {tname}>")
            elif t == "tool_result":
                tc = c.get("content","")
                if isinstance(tc, list):
                    tc = " ".join(x.get("text","") for x in tc if isinstance(x,dict))
                tc = str(tc)
                parts.append(f"<RESULT len={len(tc)}>")
        return role, "\n".join(parts)
    return role, None

def analyze(path, label):
    rows = load(path)
    out = []
    out.append(f"\n======================== {label} ========================")
    out.append(f"raw records: {len(rows)}    file_size_MB: {os.path.getsize(path)/1e6:.2f}")
    user_msgs, asst_msgs = [], []
    file_writes, file_edits = set(), set()
    bash_cmds = []
    tools_used = {}
    todos_seen = []
    skills_invoked = []
    agents_spawned = []
    for r in rows:
        role, text = role_text(r)
        if not text: continue
        if role == "user":
            if "<RESULT" not in text and "<TOOL" not in text and "<BASH" not in text:
                if text.strip():
                    user_msgs.append(text.strip())
        elif role == "assistant":
            asst_msgs.append(text)
            for m in re.finditer(r"<TOOL (\w+) ([^>]+)>", text):
                tools_used[m.group(1)] = tools_used.get(m.group(1),0)+1
                if m.group(1) == "Write": file_writes.add(m.group(2))
                if m.group(1) == "Edit": file_edits.add(m.group(2))
            for m in re.finditer(r"<BASH ([^>]+)>", text):
                bash_cmds.append(m.group(1)); tools_used["Bash"]=tools_used.get("Bash",0)+1
            for m in re.finditer(r"<TODOS [^>]+>", text):
                todos_seen.append(m.group(0))
            for m in re.finditer(r"<SKILL (\S+)>", text):
                skills_invoked.append(m.group(1))
            for m in re.finditer(r"<AGENT (\S+) :: ([^>]+)>", text):
                agents_spawned.append((m.group(1), m.group(2)))
    out.append(f"user turns: {len(user_msgs)}  assistant turns: {len(asst_msgs)}")
    out.append(f"tools usage: {sorted(tools_used.items(), key=lambda x:-x[1])[:12]}")
    out.append(f"unique Writes: {len(file_writes)}   unique Edits: {len(file_edits)}")
    out.append(f"skills invoked (all): {skills_invoked}")
    out.append(f"agents spawned ({len(agents_spawned)}, last 10): {agents_spawned[-10:]}")
    rastering_files = [f for f in (file_writes|file_edits) if "rastering" in f.lower() or "gui" in f.lower() or "raster" in f.lower()]
    out.append(f"rastering files touched ({len(rastering_files)}):")
    for f in sorted(rastering_files)[:30]:
        out.append(f"   {f}")
    out.append("\n--- FIRST USER MESSAGE ---")
    if user_msgs:
        out.append(user_msgs[0][:1500])
    out.append("\n--- LAST 8 USER MESSAGES ---")
    for i, m in enumerate(user_msgs[-8:], 1):
        n = len(user_msgs)-8+i
        out.append(f"[U-{n}] {m[:500]}")
    if todos_seen:
        out.append("\n--- LAST TODO SNAPSHOT ---")
        out.append(todos_seen[-1][:1500])
    out.append("\n--- LAST 2 ASSISTANT TURNS (compact) ---")
    for m in asst_msgs[-2:]:
        out.append("---")
        compact = re.sub(r"<RESULT len=\d+>", "<RESULT>", m)
        out.append(compact[:1800])
    print("\n".join(out))

for label, fname in SESSIONS.items():
    analyze(os.path.join(DIR, fname), label)
