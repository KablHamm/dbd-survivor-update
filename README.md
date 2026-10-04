# dbd-survivor-update — the daily roster feed for DBD Gauntlet

The **DBD Gauntlet** r1 app ships with 54 survivors baked into it. When Bhrui
Studios adds a character, this repository adds them to the app overnight,
without anyone switching a PC on and without touching the app's own build.

It is the same idea as the perk picker's feed, with one extra rule that the
perks did not need.

## What the app reads

```
https://raw.githubusercontent.com/KablHamm/dbd-survivor-update/main/survivors-update.json
```

The app paints the bundled 54 first and never waits for this file. When it
arrives, the app reads it, checks it, and adopts any character it does not have.
If the file is missing, blocked, slow, malformed, or shorter than the roster the
app already has, nothing changes and nothing on screen says so.

## The two files

| file | who writes it | what it is |
| --- | --- | --- |
| `baseline.json` | the first run, once | the 54 survivors the app already bundles, in the app's order, with every field they ship with |
| `survivors-update.json` | the daily job | the whole ordered roster, baseline slots first, new characters appended |

## The rules, and why they are the rules

**Order is never re-sorted.** The gauntlet's checkpoints are slices of the roster
in roster order — 1–10, 11–20, 21–30, 31–40, then everything left over. A
survivor who escaped at number 3 has that mark stored against their wiki slug, and
the app reads it back at whatever position that slug now sits in. So if a new
character were *inserted* into wiki order, every survivor below them would shift up
one, and every escape Adam has banked would silently jump a tier the next morning.
New characters are therefore **appended after the whole roster**, not sorted into
it. A character whose name sorts near A lands at position 55.

**Nobody is ever removed.** If the wiki drops a survivor — it has done this with
unlicensed characters — their baseline entry is served unchanged and their slot
stays, because their escapes are still marked against that slug. Removing the row
would orphan those marks.

**A smaller roster is refused, not published.** The build aborts if the page
parses into fewer survivors than the baseline holds. That is a page layout change,
not a roster change, and publishing it would wipe rows off the device.

**One page a day.** The survivor list page is fetched every run. A character's own
page is fetched only when that character is new, so a quiet week costs one request
and a release week costs two or three. Text fixes to survivors already in the app
land when the app itself is next rebuilt by hand — that is deliberate, and keeps
the job well clear of the wiki's rate limits.

## When a new survivor actually shows up

The job runs at 06:23 UTC and commits within a minute or two if the wiki lists
somebody new. The device does not poll. **The roster appears the next time the app
is opened**, which is also when the app re-reads the feed:

* fully offline — the bundled 54, no spinner, no empty state, nothing said about it;
* online — the bundled 54 paint immediately and the new characters are appended
  silently a moment later;
* on a bad file — the bundled 54, exactly as offline.

Newly adopted characters are remembered in the app's own storage, so they are
still there on a later launch with no network.

## Running it by hand

```
python tools/seed_baseline.py survivors.json       # only to rebuild the spine by hand
python tools/build_survivors_update.py                    # the scrape
python tools/roster_changed.py before.json survivors-update.json
```

`baseline.json` is written by the first run, which takes the roster the app was
itself built with and freezes it. It is never re-derived after that, even though
the app's address changes on every rehost — a spine that moved would move every
survivor's checkpoint and break the marks already banked against them.

`roster_changed.py` exits 0 when the roster is unchanged and 1 when it is not —
the `built` timestamp moving on its own is not a change, or every morning would
commit noise.

The workflow can also be run on demand: **Actions → refresh survivor roster →
Run workflow → main**.

## Checking a roster before it ships

The build refuses to write a roster that has duplicate slugs, an entry missing a
name, portrait or description, or fewer survivors than the baseline. The app
refuses the same things a second time, at read time, because the app's copy of the
feed is the one that matters. Neither check is a substitute for the other.
