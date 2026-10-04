"""Regenerate baseline.json from a survivors.json the app was built with.

    python tools/seed_baseline.py [path/to/survivors.json]

baseline.json is the fixed spine of the feed: the survivors the app already
bundles, in the order the app holds them, with every field they ship with. The
daily build reads it to decide two things that must never drift - which slot a
survivor keeps, and what to serve for one the wiki has dropped.

Run this whenever survivors.json itself is rebuilt by hand (a new release, a
data fix). It is the one file in the repository that is written by a person.
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DEFAULT = os.path.join(os.path.dirname(REPO), "survivors.json")

FIELDS = ("n", "r", "o", "dlc", "i", "t", "id", "s", "d", "slug")


def entry(p):
    """One survivor, in exactly the shape survivors.json and the feed use."""
    return {k: p.get(k, "") or "" for k in FIELDS}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    if not os.path.exists(src):
        raise SystemExit("no survivors file at %s" % src)
    roster = json.load(io.open(src, encoding="utf-8"))
    if not isinstance(roster, list) or not roster:
        raise SystemExit("%s is not a non-empty array" % src)

    order, entries, bad = [], {}, []
    for p in roster:
        e = entry(p)
        if not e["slug"] or not e["n"] or not e["i"] or not e["d"]:
            bad.append(e["n"] or e["id"] or "?")
            continue
        if e["slug"] in entries:
            bad.append("duplicate " + e["slug"])
            continue
        order.append(e["slug"])
        entries[e["slug"]] = e
    if bad:
        raise SystemExit("refusing to seed: %s" % "; ".join(bad))

    doc = {
        "note": "The survivors the app already bundles, in the app's own order. "
                "Slot order is load-bearing: the daily build never re-sorts it, "
                "so a survivor keeps the checkpoint it was played in.",
        "source": os.path.basename(src),
        "count": len(order),
        "order": order,
        "entries": entries,
    }
    path = os.path.join(REPO, "baseline.json")
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=1))
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("wrote %s: %d survivors, %d bytes" % (path, len(order), os.path.getsize(path)))


if __name__ == "__main__":
    main()
