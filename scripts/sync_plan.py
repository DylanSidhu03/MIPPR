"""Keep docs/pipeline-tracker.html (and GitHub issue text) in step with docs/PIPELINE.md.

    python scripts/sync_plan.py                 # rewrite the tracker's stage data
    python scripts/sync_plan.py --issues DIR    # also write one issue body per stage to DIR
                                                # (--branch NAME to link to a branch other than main)

PIPELINE.md is the source. The tracker starts with the tasks ticked there
already checked; a visitor's own ticks are kept in their browser.
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "docs" / "PIPELINE.md"
TRACKER = ROOT / "docs" / "pipeline-tracker.html"
REPO_URL = "https://github.com/DylanSidhu03/MIPPR/blob/{branch}"
IDS = ["scope", "capture", "truth", "prep", "seg", "measure", "classify", "validate", "batch", "web", "release"]
STORAGE_KEY = "mippr-pipeline-v2"  # bump whenever the task list changes, so saved ticks don't shift onto other tasks


def parse():
    text = PIPELINE.read_text()
    parts = re.split(r"^## ", text, flags=re.M)[1:]
    stages = []
    for part in parts:
        title, _, body = part.partition("\n")
        s = {"title": title.strip(), "tasks": [], "notes": [], "raw": body}
        current = None
        for line in body.splitlines():
            m = re.match(r"- \[( |x)\] (.*)", line)
            sub = re.match(r"  - (.*)", line)
            if m:
                current = {"text": m.group(2).strip(), "done": m.group(1) == "x", "sub": []}
                s["tasks"].append(current)
            elif sub and current:
                current["sub"].append(sub.group(1).strip())
            elif line.startswith("**Goal:**"):
                s["goal"] = line[len("**Goal:**"):].strip()
            elif line.startswith("**Flow:**"):
                s["io"] = [x.strip() for x in line[len("**Flow:**"):].split("->")]
            elif line.startswith("**In:**"):
                s["inputs"] = line[len("**In:**"):].strip()
            elif line.startswith("**Out:**"):
                s["outputs"] = line[len("**Out:**"):].strip()
            elif line.startswith("**Watch for:**"):
                s["risk"] = line[len("**Watch for:**"):].strip()
            elif line.strip() and not line.startswith(("-", " ", "*Last")):
                s["notes"].append(line.strip())
                current = None
        stages.append(s)
    return stages


def plain(md):
    """Markdown to the plain text the tracker shows."""
    md = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", md)
    return md.replace("**", "").replace("`", "")


def tracker_data(stages):
    out = []
    work = iter(IDS)
    for s in stages:
        if s["title"].startswith("Decision point"):
            out.append({"id": "gate", "gate": True, "name": s["title"],
                        "body": plain(" ".join(s["notes"])),
                        "tasks": [plain(t["text"]) for t in s["tasks"]],
                        "done": [t["done"] for t in s["tasks"]]})
            continue
        name = re.sub(r"^\d+\.\s*", "", s["title"])
        sid = next(work)
        out.append({
            "id": sid, "name": re.sub(r"\s*\(if feasible\)", "", name),
            "optional": "(if feasible)" in name,
            "goal": plain(s["goal"]), "io": [plain(x) for x in s["io"]],
            "tasks": [plain(" ".join([t["text"], *t["sub"]])) for t in s["tasks"]],
            "done": [t["done"] for t in s["tasks"]],
            "inputs": plain(s["inputs"]), "outputs": plain(s["outputs"]), "risk": plain(s["risk"]),
        })
    return out


def write_tracker(stages):
    html = TRACKER.read_text()
    data = tracker_data(stages)
    block = "const STAGES=[\n" + ",\n".join(json.dumps(d, ensure_ascii=False) for d in data) + "\n];\n"
    html, n = re.subn(r"const STAGES=\[.*?\n\];\n", lambda _: block, html, flags=re.S)
    if n != 1:
        html, n = re.subn(r"const STAGES=\[.*?\];\n", lambda _: block, html, count=1, flags=re.S)
    assert n == 1, "STAGES block not found"
    html = re.sub(r'const KEY="[^"]+";', f'const KEY="{STORAGE_KEY}";', html)
    # Start from the ticks in PIPELINE.md when the visitor has no saved state.
    old = 'let state={};try{state=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}'
    new = ('let state=null;try{state=JSON.parse(localStorage.getItem(KEY)||"null")}catch(e){}\n'
           'if(!state){state={};STAGES.forEach(s=>(s.done||[]).forEach((d,i)=>{if(d)state[s.id+":"+i]=1}))}')
    if old in html:
        html = html.replace(old, new)
    TRACKER.write_text(html)
    return data


def issue_bodies(stages, branch):
    url = REPO_URL.format(branch=branch)
    bodies = {}
    gate = next(s for s in stages if s["title"].startswith("Decision point"))
    for s in stages:
        if s["title"].startswith("Decision point"):
            continue
        num = int(s["title"].split(".")[0])
        anchor = re.sub(r"[^a-z0-9 -]", "", s["title"].lower()).replace(" ", "-")
        lines = [f"**Goal:** {s['goal']}", ""]
        lines += [n for n in s["notes"]] + ([""] if s["notes"] else [])
        if num == 10:
            lines += ["**Decision point first.** " + " ".join(gate["notes"]), ""]
            lines += [f"- [{'x' if t['done'] else ' '}] {t['text']}" for t in gate["tasks"]] + ["", "**Tasks**", ""]
        for t in s["tasks"]:
            lines.append(f"- [{'x' if t['done'] else ' '}] {t['text']}")
            lines += [f"  - {x}" for x in t["sub"]]
        lines += ["", f"**In:** {s['inputs']}", f"**Out:** {s['outputs']}", f"**Watch for:** {s['risk']}", "",
                  f"See [docs/PIPELINE.md]({url}/docs/PIPELINE.md#{anchor})."]
        # Relative repo links in PIPELINE.md would break inside an issue.
        body = "\n".join(lines)
        body = re.sub(r"\]\((?:\.\./)?(CLAUDE\.md|prototype/[^)]*)\)", rf"]({url}/\1)", body)
        body = re.sub(r"\]\(([A-Z_]+\.md)\)", rf"]({url}/docs/\1)", body)
        bodies[num] = body
    return bodies


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--issues", help="folder to write issue_<n>.md bodies into")
    ap.add_argument("--branch", default="main", help="branch that issue links point to")
    a = ap.parse_args()
    stages = parse()
    data = write_tracker(stages)
    done = sum(sum(s["done"]) for s in data)
    total = sum(len(s["tasks"]) for s in data)
    print(f"tracker: {len(data)} sections, {done} of {total} tasks ticked")
    if a.issues:
        out = Path(a.issues)
        out.mkdir(parents=True, exist_ok=True)
        for num, body in issue_bodies(stages, a.branch).items():
            (out / f"issue_{num}.md").write_text(body)
        print(f"issue bodies -> {out}")


if __name__ == "__main__":
    main()
