"""Rebuild survivors-update.json - the daily feed the DBD Gauntlet app reads.

    python tools/build_survivors_update.py

Source of truth is the rendered page at deadbydaylight.wiki.gg, the same page
the app was built from. Portraits come from wiki.gg; the old Fandom/Gamepedia
image URLs are long deprecated and are not used anywhere here.

What this will not do
---------------------
* It never re-sorts. The order in baseline.json is the order the app holds, and
  a survivor keeps the checkpoint slot they were played in. A character added to
  the wiki is APPENDED after the whole existing roster, so nobody's escape
  counts jump a tier overnight.
* It never removes anybody. If the wiki drops a survivor, their baseline entry
  is served unchanged and their slot stays. (wiki.gg has done this with
  unlicensed survivors before, and the marks on their row have to keep working.)
* It never writes a smaller roster. If the page parses into fewer blocks than
  the baseline holds, that is a layout change rather than a roster change, and
  the run stops before writing. A truncated feed must never reach the app.

Cost: one page fetch a day. Character pages are fetched only for survivors the
baseline does not already have, so a quiet week is a single request. Text fixes
to a survivor already in the app arrive when the app itself is next rebuilt by
hand - that is deliberate: refreshing 54 pages every morning would buy very
little and run the wiki's rate limits into the ground.
"""
import datetime
import html
import io
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ORIGIN = "https://deadbydaylight.wiki.gg"
LIST_URL = ORIGIN + "/wiki/Survivors"
UA = "OS3 DBD Gauntlet survivor feed"
TAG = re.compile(r"<[^>]+>")
FIELDS = ("n", "r", "o", "dlc", "i", "t", "id", "s", "d", "slug")

# Two typos in the wiki's own infobox Role line, corrected here so they do not
# read as bugs in the app. Applied only on an exact match, and reported.
ROLE_FIXES = {
    "Harded Archaeologist": "Hardened Archaeologist",
    "Brillant High School Student": "Brilliant High School Student",
}

BOILER = re.compile(
    r"(?i)(this (?:description|entry) is based on the changes|"
    r"based on the changes announced|upcoming patch)")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def fetch(url, attempts=3):
    """One wiki page, retried politely. No caching: CI runs it once a day."""
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "replace")
        except Exception as exc:                       # noqa: BLE001 - reported, retried
            last = exc
            time.sleep(1.5 * (i + 1))
    raise SystemExit("could not fetch %s: %s" % (url, last))


def clean(s):
    """Text out of one HTML cell or paragraph: no icon links, no tags, no entities."""
    s = re.sub(r"""(?is)<span[^>]*class="[^"]*iconLink[^"]*".*?</span>""", "", s)
    s = re.sub(r"(?is)<table.*?</table>", " ", s)
    s = re.sub(r"(?is)<style.*?</style>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</p>", "", s)
    s = re.sub(r"(?i)</?(td|th|tr|table|div|span|ul|ol|li|strong|em|b|i|p|sup|sub)[^>]*>", "", s)
    s = TAG.sub("", s)
    s = html.unescape(s)
    s = s.replace(chr(0xA0), ' ').replace(chr(0x200E), '').replace(chr(0x200F), '')
    return re.sub(r"[ \t]+", " ", s).strip()


def listed_survivors(page):
    """Ordered (name, slug, portrait, id) from the List_of_Survivors section.

    The section is a run of identical inline-flex blocks, one per character:
    a link to the character's page, then a charPortraitWrapper holding the
    portrait image. Some blocks wrap the name in a "New Survivor" label, so the
    blocks are split rather than matched with one big pattern - a pattern that
    skips four characters without saying so is exactly the bug this avoids.
    """
    i0 = page.find('id="List_of_Survivors"')
    i1 = page.find('id="List_of_Survivor_Items"')
    if i0 < 0 or i1 < i0:
        raise SystemExit("page layout changed: List_of_Survivors anchors not found")
    sec = page[i0:i1]
    blocks = sec.split('<div style="display: inline-flex; flex-direction: column; '
                       'text-align:center; margin-bottom: 35px;">')[1:]
    out = []
    for b in blocks:
        link = re.search(r'<a href="(/wiki/[^"#]+)" title="([^"]+)">', b)
        img = re.search(r'<img[^>]+src="(/images/[^"]*_Portrait\.png[^"]*)"', b)
        if not link or not img:
            raise SystemExit("page layout changed: a survivor block lost its link or portrait")
        slug, title = link.groups()
        url = ORIGIN + html.unescape(img.group(1))
        cid = re.search(r"S\d+", url)
        out.append({
            "n": html.unescape(title).strip(),
            "slug": slug[len("/wiki/"):],
            "i": url,
            "id": cid.group(0) if cid else "",
        })
    return out


def infobox(raw, field):
    """One titleColumn/valueColumn row from the character infobox."""
    for m in re.finditer(r"(?is)<td class=\"titleColumn[^\"]*\">(.*?)</td>\s*"
                         r"<td class=\"valueColumn[^\"]*\">(.*?)</td>", raw):
        if clean(m.group(1)).rstrip(":") == field:
            return clean(m.group(2))
    return ""


def overview(raw):
    """The Overview section's paragraphs, with icon links and images stripped."""
    i0 = raw.find('id="Overview"')
    if i0 < 0:
        return []
    nxt = re.search(r'<span class="mw-headline" id="([^"]+)"', raw[i0 + 10:])
    sec = raw[i0: i0 + 10 + nxt.start()] if nxt else raw[i0:]
    paras = []
    for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", sec):
        t = clean(p)
        if len(t) > 2 and not re.match(r"(?i)^(contents|retrieved from)", t):
            paras.append(t)
    return paras


def sentences(text):
    return [p for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]


def short_text(paras, limit=185):
    """A whole-sentence summary for the roll screen, same rule as the app build."""
    pool = [p for p in paras if not BOILER.search(p)]
    if not pool:
        return ""
    body = pool[-1]
    out = ""
    for s in sentences(body):
        if not s:
            continue
        if not out and len(s) > limit:
            cut = s[:limit]
            return cut[:cut.rfind(" ")].rstrip(",;:") + "…"
        if out and len(out) + 1 + len(s) > limit:
            break
        out = (out + " " + s).strip()
    return out or body[:limit]


def full_text(paras):
    return "\n\n".join(p for p in paras if p)


def thumb(url, w):
    """A wiki.gg thumb of the full-size portrait: 150px for rows, 250px for the card."""
    base = url.split("?")[0]
    name = base.rsplit("/", 1)[1]
    return "%s/images/thumb/%s/%dpx-%s" % (ORIGIN, name, w, name)


def character(item):
    """One new survivor's full entry, from their own wiki page."""
    raw = fetch(ORIGIN + "/wiki/" + item["slug"])
    paras = overview(raw)
    title = re.search(r'<th class="center bold" colspan="2">(.*?)</th>', raw, re.S)
    name = clean(title.group(1)) if title else item["n"]
    role = infobox(raw, "Role")
    role = ROLE_FIXES.get(role, role)
    pid = infobox(raw, "CharID")
    return {
        "n": name or item["n"],
        "r": role,
        "o": infobox(raw, "Origin"),
        "dlc": infobox(raw, "DLC"),
        "i": thumb(item["i"], 250),
        "t": thumb(item["i"], 150),
        "id": pid or item["id"],
        "s": short_text(paras),
        "d": full_text(paras),
        "slug": item["slug"],
    }


def usable(p):
    """What the app insists on before it will adopt a survivor."""
    return (isinstance(p, dict) and p.get("slug") and p.get("n")
            and p.get("i") and p.get("t") and p.get("d"))


def main():
    base_path = os.path.join(REPO, "baseline.json")
    if not os.path.exists(base_path):
        raise SystemExit("no baseline.json - run tools/seed_baseline.py first")
    base = json.load(io.open(base_path, encoding="utf-8"))
    order, entries = base.get("order") or [], base.get("entries") or {}
    if not order or len(order) != len(entries):
        raise SystemExit("baseline.json is broken: %d slots, %d entries" % (len(order), len(entries)))
    for slug in order:
        if not usable(entries.get(slug)):
            raise SystemExit("baseline entry for %s is incomplete" % slug)

    page = fetch(LIST_URL)
    listed = listed_survivors(page)
    prose = clean(page)
    stated = re.search(r"currently\s*([\d,]+)\s*Survivors", prose)

    # The guard that matters: fewer blocks than the baseline means the page
    # changed shape, not that the roster shrank.
    if len(listed) < len(order):
        raise SystemExit(
            "refusing to write: the page parsed %d survivors but the baseline holds %d. "
            "That is a page layout change, not a roster change."
            % (len(listed), len(order)))
    if len(listed) > 200:
        raise SystemExit("refusing to write: %d survivors parsed, which is not a roster" % len(listed))

    fresh = {}
    for item in listed:
        fresh.setdefault(item["slug"], item)

    new_slugs = [s for s in fresh if s not in entries]
    report = ["baseline %d survivors, wiki lists %d%s" % (
        len(order), len(listed),
        ", wiki states %s" % stated.group(1) if stated else "")]

    added = []
    for slug in new_slugs:
        try:
            e = character(fresh[slug])
        except SystemExit as exc:
            # a single new character failing is skipped, never half-written
            report.append("  FETCH FAIL %s: %s" % (slug, exc))
            continue
        if not usable(e):
            report.append("  INCOMPLETE %s (%s) - skipped" % (e.get("n", slug), slug))
            continue
        added.append(e)
        report.append("  + %-22s %-4s %-28s short=%3d full=%3d | %s" % (
            e["n"][:22], e["id"] or "-", (e["r"] or "-")[:28], len(e["s"]), len(e["d"]),
            (e["s"][:64] or "-") + ("..." if len(e["s"]) > 64 else "")))
        time.sleep(0.2)

    # baseline order first, every slot kept; then whatever is new, appended
    roster = [dict(entries[s], slug=s) for s in order] + added

    slugs = [p["slug"] for p in roster]
    if len(set(slugs)) != len(slugs):
        raise SystemExit("refusing to write: duplicate slugs in the roster")
    if len(roster) < len(order):
        raise SystemExit("refusing to write: the roster is smaller than the baseline")
    for p in roster:
        if not usable(p):
            raise SystemExit("refusing to write: incomplete entry %s" % p.get("slug"))

    doc = {
        "meta": {
            "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": LIST_URL,
            "baseline": len(order),
            "count": len(roster),
            "new": len(added),
            "newSlugs": [p["slug"] for p in added],
            "wikiListed": len(listed),
            "wikiStated": stated.group(1) if stated else "",
            "keptMissing": len([s for s in order if s not in fresh]),
        },
        "roster": roster,
    }
    path = os.path.join(REPO, "survivors-update.json")
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    report.insert(0, "wrote %s: %d survivors (%d new), %d bytes" % (
        path, len(roster), len(added), os.path.getsize(path)))
    print("\n".join(report))


if __name__ == "__main__":
    main()
