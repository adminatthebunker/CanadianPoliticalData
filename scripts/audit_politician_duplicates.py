"""Cross-jurisdiction formal-vs-colloquial duplicate-politician audit.

Candidate pair = same (level, province), fold-equal surname, term
windows overlapping (or either row termless), and first names related
by identity / containment / nickname fold / parenthesized nickname /
initials. Reports evidence + impact so pairs can be reviewed before any
merge. Read-only.
"""
import asyncio, os, re, sys, unicodedata
sys.path.insert(0, "/app")
from src.db import Database

NICK = {
    "mike": "michael", "doug": "douglas", "art": "arthur", "bill": "william",
    "bob": "robert", "rob": "robert", "dave": "david", "dan": "daniel",
    "jim": "james", "joe": "joseph", "tom": "thomas", "dick": "richard",
    "rick": "richard", "rich": "richard", "ted": "edward", "ed": "edward",
    "fred": "frederick", "len": "leonard", "ken": "kenneth", "ron": "ronald",
    "don": "donald", "steve": "steven", "greg": "gregory", "pat": "patricia",
    "sue": "susan", "liz": "elizabeth", "beth": "elizabeth",
    "kathy": "kathleen", "cathy": "catherine", "jenny": "jennifer",
    "sandy": "alexander", "alex": "alexander", "tony": "anthony",
    "andy": "andrew", "chris": "christopher", "nick": "nicholas",
    "sam": "samuel", "gord": "gordon", "gerry": "gerald", "jerry": "gerald",
    "terry": "terrence", "walt": "walter", "norm": "norman",
    "stan": "stanley", "vic": "victor", "ray": "raymond", "al": "albert",
    "herb": "herbert", "frank": "francis", "gene": "eugene",
    "phil": "philip", "vern": "vernon", "larry": "lawrence",
    "barb": "barbara", "deb": "deborah", "debbie": "deborah",
    "marg": "margaret", "peggy": "margaret", "judy": "judith",
    "moe": "munmohan", "jack": "john", "hank": "henry", "harry": "henry",
    "bernie": "bernard", "wally": "walter", "christy": "christina",
}

def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("\xa0", " ").lower().replace("-", " ").replace(".", " ")
    return re.sub(r"\s+", " ", s).strip()

def fold(tok):
    return NICK.get(tok, tok)

def paren_nick(name):
    m = re.search(r"\(([^)]{2,20})\)", name or "")
    return norm(m.group(1)) if m else None

def first_related(a, b):
    """(evidence, why) — are these first-name/full-name pairs the same person?"""
    fa, fb = norm(a["first_name"]), norm(b["first_name"])
    na, nb = norm(a["name"]), norm(b["name"])
    pa, pb = paren_nick(a["name"]), paren_nick(b["name"])
    if not fa or not fb:
        return None
    ta, tb = fa.split(" ")[0], fb.split(" ")[0]
    if fa == fb and na != nb:
        return ("high", "identical first name, variant display name")
    if fold(ta) == fold(tb) and ta != tb:
        return ("high", f"nickname fold {ta}<->{tb}")
    if pa and (pa == tb or pa == fold(tb)):
        return ("high", f"parenthesized nickname '{pa}'")
    if pb and (pb == ta or pb == fold(ta)):
        return ("high", f"parenthesized nickname '{pb}'")
    # containment: "dan" token inside "arthur daniel" (also folded)
    toks_a = set(fa.split(" ")) | {fold(t) for t in fa.split(" ")}
    toks_b = set(fb.split(" ")) | {fold(t) for t in fb.split(" ")}
    if (ta in toks_b or fold(ta) in toks_b) or (tb in toks_a or fold(tb) in toks_a):
        return ("medium", "first-name token containment")
    # initial-only vs name: "j" matches "john"
    if (len(ta) == 1 and tb.startswith(ta)) or (len(tb) == 1 and ta.startswith(tb)):
        return ("low", "initial-vs-name")
    return None

async def main():
    dsn = os.environ.get("DATABASE_URL") or f"postgresql://sw:{os.environ.get('DB_PASSWORD','')}@db/sovereignwatch"
    db = Database(dsn)
    await db.connect()
    rows = await db.fetch("""
        SELECT p.id::text, p.name, p.first_name, p.last_name, p.level,
               p.province_territory AS prov, p.source_id, p.is_active,
               p.lims_member_id IS NOT NULL OR p.qc_assnat_id IS NOT NULL
                 OR p.openparliament_slug IS NOT NULL OR p.ola_member_id IS NOT NULL
                 OR p.ab_assembly_mid IS NOT NULL OR p.mb_assembly_slug IS NOT NULL
                 OR p.nslegislature_slug IS NOT NULL OR p.nt_mla_slug IS NOT NULL
                 OR p.sk_assembly_slug IS NOT NULL AS has_native_id,
               (SELECT count(*) FROM speeches s WHERE s.politician_id=p.id) AS speeches,
               (SELECT count(*) FROM politician_terms t WHERE t.politician_id=p.id) AS terms,
               (SELECT min(t.started_at) FROM politician_terms t WHERE t.politician_id=p.id) AS t_min,
               (SELECT max(coalesce(t.ended_at, now())) FROM politician_terms t WHERE t.politician_id=p.id) AS t_max
          FROM politicians p
         WHERE p.last_name IS NOT NULL AND p.first_name IS NOT NULL
    """)
    by_key = {}
    for r in rows:
        key = (r["level"], r["prov"] or "", norm(r["last_name"]))
        by_key.setdefault(key, []).append(dict(r))

    found = []
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                rel = first_related(a, b)
                if not rel:
                    continue
                # window overlap (termless rows treated as overlapping)
                if a["t_min"] and b["t_min"]:
                    if not (a["t_min"] < b["t_max"] and b["t_min"] < a["t_max"]):
                        continue
                found.append((key, a, b, rel))

    found.sort(key=lambda x: -(x[1]["speeches"] + x[2]["speeches"]))
    print(f"candidate duplicate pairs: {len(found)}\n")
    for key, a, b, (ev, why) in found:
        lvl, prov, _ = key
        print(f"[{ev.upper()}] {lvl}/{prov or '—'}: {why}")
        for r in (a, b):
            print(f"   {r['id'][:8]}  {r['name']!r:42s} nat_id={'Y' if r['has_native_id'] else '-'} "
                  f"active={'Y' if r['is_active'] else '-'} terms={r['terms']} speeches={r['speeches']} "
                  f"src={str(r['source_id'])[:44]}")
        print()
    await db.close()

asyncio.run(main())