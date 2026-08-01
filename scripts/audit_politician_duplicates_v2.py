"""MEDIUM-tier duplicate review pass — refined discriminators.

Buckets every same-surname/window-overlap/first-name-related pair:
  DISTINCT   both rows carry distinct native ids (Cooke rule), or term
             constituencies differ.
  STRONG     constituencies agree (or one side has none) AND the pair
             shows the split-brain signature (data complementary) or a
             prefix/containment first-name relation with an orphan row.
  WEAK       everything else (unverifiable containment, e.g. QC Jean-X).
Read-only report.
"""
import asyncio, os, re, sys, unicodedata
sys.path.insert(0, "/app")
from src.db import Database

NICK = {"mike":"michael","doug":"douglas","art":"arthur","bill":"william",
"bob":"robert","rob":"robert","dave":"david","dan":"daniel","jim":"james",
"joe":"joseph","tom":"thomas","dick":"richard","rick":"richard","ted":"edward",
"ed":"edward","fred":"frederick","len":"leonard","ken":"kenneth","ron":"ronald",
"don":"donald","steve":"steven","greg":"gregory","pat":"patricia","sue":"susan",
"liz":"elizabeth","kathy":"kathleen","cathy":"catherine","jenny":"jennifer",
"sandy":"alexander","alex":"alexander","tony":"anthony","andy":"andrew",
"chris":"christopher","nick":"nicholas","sam":"samuel","gord":"gordon",
"gerry":"gerald","jerry":"gerald","terry":"terrence","norm":"norman",
"stan":"stanley","vic":"victor","ray":"raymond","al":"albert","herb":"herbert",
"frank":"francis","gene":"eugene","phil":"philip","vern":"vernon",
"larry":"lawrence","judy":"judith","moe":"munmohan","jack":"john",
"bernie":"bernard","harry":"henry","christy":"christina","walt":"walter"}

def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+"," ", s.replace("\xa0"," ").lower().replace("-"," ").replace("."," ")).strip()

def fold(t): return NICK.get(t, t)

def norm_const(c):
    if not c: return None
    return norm(c.split("/")[-1])

async def main():
    dsn = os.environ.get("DATABASE_URL") or f"postgresql://sw:{os.environ.get('DB_PASSWORD','')}@db/sovereignwatch"
    db = Database(dsn); await db.connect()
    rows = await db.fetch("""
        SELECT p.id::text, p.name, p.first_name, p.last_name, p.level,
               p.province_territory AS prov, p.source_id, p.is_active,
               (SELECT count(DISTINCT x) FROM unnest(ARRAY[
                 p.lims_member_id::text, p.qc_assnat_id::text, p.openparliament_slug,
                 p.ola_member_id::text, p.ab_assembly_mid, p.mb_assembly_slug,
                 p.nslegislature_slug, p.nt_mla_slug, p.sk_assembly_slug]) AS x
                 WHERE x IS NOT NULL) > 0 AS has_native_id,
               (SELECT count(*) FROM speeches s WHERE s.politician_id=p.id) AS speeches,
               (SELECT count(*) FROM politician_terms t WHERE t.politician_id=p.id) AS terms,
               (SELECT min(t.started_at) FROM politician_terms t WHERE t.politician_id=p.id) AS t_min,
               (SELECT max(coalesce(t.ended_at, now())) FROM politician_terms t WHERE t.politician_id=p.id) AS t_max,
               (SELECT array_agg(DISTINCT t.constituency_id) FROM politician_terms t
                 WHERE t.politician_id=p.id AND t.constituency_id IS NOT NULL) AS consts
          FROM politicians p
         WHERE p.last_name IS NOT NULL AND p.first_name IS NOT NULL
    """)
    by_key = {}
    for r in rows:
        by_key.setdefault((r["level"], r["prov"] or "", norm(r["last_name"])), []).append(dict(r))

    buckets = {"DISTINCT": [], "STRONG": [], "WEAK": []}
    for key, group in by_key.items():
        if len(group) < 2: continue
        for i in range(len(group)):
            for j in range(i+1, len(group)):
                a, b = group[i], group[j]
                fa, fb = norm(a["first_name"]), norm(b["first_name"])
                if not fa or not fb: continue
                ta, tb = fa.split(" ")[0], fb.split(" ")[0]
                related = (
                    fa == fb or fold(ta) == fold(tb)
                    or ta in fb.split(" ") or tb in fa.split(" ")
                    or fold(ta) in [fold(x) for x in fb.split(" ")]
                    or fold(tb) in [fold(x) for x in fa.split(" ")]
                    or (len(ta)==1 and tb.startswith(ta)) or (len(tb)==1 and ta.startswith(tb))
                )
                if not related: continue
                if a["t_min"] and b["t_min"]:
                    if not (a["t_min"] < b["t_max"] and b["t_min"] < a["t_max"]): continue
                # discriminators
                ca = {norm_const(c) for c in (a["consts"] or [])}
                cb = {norm_const(c) for c in (b["consts"] or [])}
                const_overlap = bool(ca and cb and (ca & cb))
                const_conflict = bool(ca and cb and not (ca & cb))
                both_native = a["has_native_id"] and b["has_native_id"]
                one_orphan = a["has_native_id"] != b["has_native_id"]
                split_brain = ((a["speeches"]>0) != (b["speeches"]>0)) and ((a["terms"]>0) != (b["terms"]>0))
                exact_first = fa == fb or fold(ta) == fold(tb)

                if both_native and not const_overlap:
                    bucket = "DISTINCT"
                elif const_conflict:
                    bucket = "DISTINCT"
                elif const_overlap and (exact_first or one_orphan):
                    bucket = "STRONG"
                elif one_orphan and exact_first and (split_brain or min(a["speeches"],b["speeches"])==0):
                    bucket = "STRONG"
                else:
                    bucket = "WEAK"
                buckets[bucket].append((key, a, b, const_overlap, split_brain))

    for name in ("STRONG", "WEAK", "DISTINCT"):
        items = buckets[name]
        print(f"### {name}: {len(items)}")
        if name == "DISTINCT": continue
        for key, a, b, co, sb in sorted(items, key=lambda x: -(x[1]["speeches"]+x[2]["speeches"]))[:60 if name=="STRONG" else 25]:
            lvl, prov, _ = key
            print(f"  {lvl}/{prov or '—'} const_match={'Y' if co else '-'} split_brain={'Y' if sb else '-'}")
            for r in (a, b):
                print(f"    {r['id'][:8]} {r['name']!r:40s} nat={'Y' if r['has_native_id'] else '-'} act={'Y' if r['is_active'] else '-'} "
                      f"t={r['terms']} sp={r['speeches']} src={str(r['source_id'])[:40]}")
        print()
    await db.close()

asyncio.run(main())