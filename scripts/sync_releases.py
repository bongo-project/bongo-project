#!/usr/bin/env python3
"""Write _data/releases.json from the v* tags of the Bongo code repository.

Usage: scripts/sync_releases.py [path-to-bongo-checkout]   (default: ../bongo)

Releases are grouped by minor version (x.y), newest first. An annotated tag
contributes its subject and message; a lightweight tag, or an annotated tag
whose message is only the version, contributes the version and date only.
"""
import json
import pathlib
import re
import subprocess
import sys

RELEASE_URL = "https://github.com/bongo-project/bongo/releases/tag/"
SEP = "\x1f"
END = "\x1e"


def escape(line: str) -> str:
    # Tag messages are plain text; keep Markdown from reading them as markup.
    return re.sub(r"([\\*_<>\[\]|$])", r"\\\1", line)


def to_markdown(body: str, level: int) -> str:
    lines = body.rstrip().splitlines()
    out = []
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        is_item = line.startswith("- ")
        if line and not is_item and not line[0].isspace() and nxt.startswith("- "):
            out.extend(["", "#" * level + " " + escape(line.strip()), ""])
        elif is_item:
            out.append("- " + escape(line[2:]))
        else:
            out.append(escape(line))
    return "\n".join(out).strip() + "\n"


def main() -> int:
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "../bongo").resolve()
    site = pathlib.Path(__file__).resolve().parent.parent
    fmt = SEP.join(["%(refname:short)", "%(objecttype)", "%(creatordate:short)", "%(contents:subject)", "%(contents:body)"]) + END
    raw = subprocess.run(
        ["git", "-C", str(src), "for-each-ref", "--sort=-creatordate", "--format=" + fmt, "refs/tags/v*"],
        check=True, capture_output=True, text=True,
    ).stdout
    groups = {}
    order = []
    for rec in raw.split(END):
        rec = rec.strip("\n")
        if not rec:
            continue
        tag, kind, date, subject, body = (rec.split(SEP) + [""] * 5)[:5]
        m = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", tag)
        if not m:
            continue
        minor = "%s.%s" % (m.group(1), m.group(2))
        title, notes = "", ""
        if kind == "tag":
            title = re.sub(r"^(Release\s+)?" + re.escape(tag) + r":?\s*", "", subject.strip()).strip()
            notes = body.strip()
        entry = {
            "version": tag,
            "date": date,
            "title": title,
            "url": RELEASE_URL + tag,
            "annotated": kind == "tag",
            "patch": int(m.group(3)),
        }
        if minor not in groups:
            groups[minor] = {"minor": minor, "releases": []}
            order.append(minor)
        entry["notes_md"] = notes
        groups[minor]["releases"].append(entry)
    result = []
    for minor in order:
        rel = sorted(groups[minor]["releases"], key=lambda e: -e["patch"])
        base = next((e for e in rel if e["patch"] == 0), rel[-1])
        patches = [e for e in rel if e is not base]
        base["notes"] = to_markdown(base.pop("notes_md"), 3) if base["notes_md"] else ""
        for p in patches:
            p["notes"] = to_markdown(p.pop("notes_md"), 4) if p["notes_md"] else ""
        result.append({"minor": minor, "release": base, "patches": patches})
    (site / "_data").mkdir(exist_ok=True)
    (site / "_data" / "releases.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print("wrote %d minor releases, %d tags" % (len(result), sum(1 + len(g["patches"]) for g in result)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
