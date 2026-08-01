"""MEDIUM-review merge: exact-name one-native-one-orphan duplicate pairs.

Rules (conservative by construction):
  - normalized FULL names must be EXACTLY equal (accents/hyphens/dots
    folded) — prefix/containment pairs (Jean-Louis vs Jean-Paul) are
    never touched;
  - exactly one row carries a native legislature id (canonical); the
    orphan must NOT (Cooke rule inverse);
  - same level + province; term windows overlap or either side termless;
  - canonical keeps its native id; the orphan's source_id MOVES onto
    the canonical so source-keyed ingests converge (id-keyed ingests
    keep matching via the native id column);
  - term moves are overlap-guarded (drop orphan terms whose window the
    canonical already covers);
  - groups where both rows hold >50 speeches are skipped + reported.

Prints every action. Applies in one transaction.
"""
import asyncio, os, re, sys, unicodedata
sys.path.insert(0, "/app")
from src.db import Database

def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+"," ", s.replace("\xa0"," ").lower().replace("-"," ").replace("."," ").replace(",", " ")).strip()

async def main():
    dsn = os.environ.get("DATABASE_URL") or f"postgresql://sw:{os.environ.get('DB_PASSWORD','')}@db/sovereignwatch"
    db = Database(dsn); await db.connect()
    rows = await db.fetch("""
        SELECT p.id::text, p.name, p.level, p.province_territory AS prov,
               p.source_id, p.is_active,
               (p.lims_member_id IS NOT NULL OR p.qc_assnat_id IS NOT NULL
                 OR p.openparliament_slug IS NOT NULL OR p.ola_member_id IS NOT NULL
                 OR p.ab_assembly_mid IS NOT NULL OR p.mb_assembly_slug IS NOT NULL
                 OR p.nslegislature_slug IS NOT NULL OR p.nt_mla_slug IS NOT NULL
                 OR p.sk_assembly_slug IS NOT NULL) AS has_native,
               (SELECT count(*) FROM speeches s WHERE s.politician_id=p.id) AS speeches,
               (SELECT count(*) FROM politician_terms t WHERE t.politician_id=p.id) AS terms,
               (SELECT min(t.started_at) FROM politician_terms t WHERE t.politician_id=p.id) AS t_min,
               (SELECT max(coalesce(t.ended_at, now())) FROM politician_terms t WHERE t.politician_id=p.id) AS t_max
          FROM politicians p WHERE p.name IS NOT NULL
    """)
    groups = {}
    for r in rows:
        groups.setdefault((r["level"], r["prov"] or "", norm(r["name"])), []).append(dict(r))

    pairs, skipped = [], []
    for key, g in groups.items():
        if len(g) < 2: continue
        natives = [r for r in g if r["has_native"]]
        orphans = [r for r in g if not r["has_native"]]
        if len(natives) != 1 or not orphans: continue
        canon = natives[0]
        for orphan in orphans:
            if canon["t_min"] and orphan["t_min"]:
                if not (canon["t_min"] < orphan["t_max"] and orphan["t_min"] < canon["t_max"]):
                    continue
            if min(canon["speeches"], orphan["speeches"]) > 50:
                skipped.append((key, canon, orphan)); continue
            pairs.append((key, canon, orphan))

    print(f"mergeable exact-name pairs: {len(pairs)}; skipped (both speech-heavy): {len(skipped)}")
    for key, c, o in skipped:
        print(f"  SKIP {key[0]}/{key[1]}: {c['name']!r} — both rows speech-heavy")

    by_prov = {}
    for key, c, o in pairs:
        by_prov[(key[0], key[1])] = by_prov.get((key[0], key[1]), 0) + 1
    print("by jurisdiction:", dict(sorted(by_prov.items(), key=lambda x: -x[1])))

    if os.environ.get("APPLY") != "1":
        print("\nDRY RUN (set APPLY=1 to execute). Sample pairs:")
        for key, c, o in pairs[:15]:
            print(f"  {key[0]}/{key[1]}: canon {c['id'][:8]} {c['name']!r} (t={c['terms']} sp={c['speeches']}) "
                  f"<- orphan {o['id'][:8]} src={str(o['source_id'])[:50]} (t={o['terms']} sp={o['speeches']})")
        await db.close(); return

    moved_terms = moved_speeches = 0
    async with db.pool.acquire() as con:
        async with con.transaction():
            for key, c, o in pairs:
                await con.execute(
                    """DELETE FROM politician_terms t WHERE t.politician_id=$1::uuid
                       AND EXISTS (SELECT 1 FROM politician_terms ct WHERE ct.politician_id=$2::uuid
                         AND ct.level=t.level
                         AND ct.started_at < coalesce(t.ended_at,'infinity'::timestamptz)
                         AND coalesce(ct.ended_at,'infinity'::timestamptz) > t.started_at)""",
                    o["id"], c["id"])
                r1 = await con.execute(
                    "UPDATE politician_terms SET politician_id=$2::uuid WHERE politician_id=$1::uuid",
                    o["id"], c["id"])
                moved_terms += int(r1.split(" ")[-1])
                r2 = await con.execute(
                    "UPDATE speeches SET politician_id=$2::uuid WHERE politician_id=$1::uuid",
                    o["id"], c["id"])
                moved_speeches += int(r2.split(" ")[-1])
                await con.execute(
                    "UPDATE vote_positions SET politician_id=$2::uuid WHERE politician_id=$1::uuid",
                    o["id"], c["id"])
                await con.execute(
                    """UPDATE politician_socials ps SET politician_id=$2::uuid
                       WHERE ps.politician_id=$1::uuid
                         AND NOT EXISTS (SELECT 1 FROM politician_socials x
                              WHERE x.politician_id=$2::uuid AND x.platform=ps.platform
                                AND lower(x.handle)=lower(ps.handle))""",
                    o["id"], c["id"])
                await con.execute("DELETE FROM politician_socials WHERE politician_id=$1::uuid", o["id"])
                await con.execute("DELETE FROM politician_committees WHERE politician_id=$1::uuid", o["id"])
                await con.execute("DELETE FROM politician_offices WHERE politician_id=$1::uuid", o["id"])
                osrc = o["source_id"]
                await con.execute(
                    "UPDATE politicians SET source_id = id::text || ':merged' WHERE id=$1::uuid", o["id"])
                if osrc and not osrc.endswith(":merged"):
                    await con.execute(
                        "UPDATE politicians SET source_id=$2, updated_at=now() WHERE id=$1::uuid", c["id"], osrc)
                await con.execute("DELETE FROM politicians WHERE id=$1::uuid", o["id"])
    print(f"APPLIED: {len(pairs)} orphans merged; terms moved {moved_terms}; speeches moved {moved_speeches}")
    await db.close()

asyncio.run(main())