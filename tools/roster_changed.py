"""Did the rebuild actually change the roster?

    python tools/roster_changed.py <published.json> <rebuilt.json>

Exit 0 when the roster is unchanged, 1 when it is not. The `built` timestamp
moves on every run and is deliberately not part of the answer - otherwise every
daily run would look like a change and the commit would be noise.

The comparison is on the thing that matters: the ordered list of slugs, plus
the fields of each entry. A wiki text fix to a survivor that is already in the
app does count as a change, and says so.

Exit 2 is used for "the rebuild is not usable", which the workflow refuses to
commit - a roster that lost survivors is a broken scrape, not a small update.
"""
import io
import json
import sys


def load(path):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except (IOError, ValueError):
        return None


FIELDS = ("n", "r", "o", "dlc", "i", "t", "id", "s", "d", "slug")


def entries_of(doc):
    """The roster out of either shape: the {meta, roster} feed, or a bare array."""
    if isinstance(doc, dict):
        return doc.get("roster")
    return doc


def shape(doc):
    """slug -> the fields that can change, so a rebuild is compared on content."""
    out = {}
    for p in (entries_of(doc) or []):
        if isinstance(p, dict):
            out[p.get("slug", "")] = tuple(p.get(k, "") or "" for k in FIELDS)
    return out


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    before, after = load(sys.argv[1]), load(sys.argv[2])

    if after is None:
        raise SystemExit("the rebuilt roster is unreadable: %s" % sys.argv[2])
    if not after:
        raise SystemExit("the rebuilt roster is empty")

    if before is None:
        print("no usable roster published yet - this run is the first")
        return 1

    was, now = shape(before), shape(after)
    if not was:
        print("no usable roster published yet - this run is the first")
        return 1

    was_list = entries_of(before) or []
    now_list = entries_of(after) or []
    added = [p.get("slug", "") for p in now_list if p.get("slug") and p["slug"] not in was]
    dropped = [p.get("slug", "") for p in was_list if p.get("slug") and p["slug"] not in now]
    # a survivor leaving the wiki never removes their slot - see build_survivors_update
    if dropped:
        print("  ! dropped from the rebuilt roster (%d): %s" % (
            len(dropped), ", ".join(dropped[:20])))
    edited = sorted(s for s in now if s in was and now[s] != was[s])

    if not added and not edited:
        print("unchanged: %d survivors" % len(now))
        return 0

    for s in added:
        who = next((p.get("n", "") for p in now_list if p.get("slug") == s), s)
        print("  + %s (%s)" % (who, s))
    for s in edited:
        print("  ~ %s" % s)
    print("changed: %d survivors (%d new, %d edited)" % (len(now), len(added), len(edited)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
