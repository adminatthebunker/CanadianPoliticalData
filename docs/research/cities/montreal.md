# Montréal — Municipal Data Research

> Standalone research dossier for the Ville de Montréal. Cross-cutting context lives in [`overview.md`](./overview.md).

**Conseil:** Conseil municipal de Montréal | **Website:** https://montreal.ca/ | **Seats:** 65 (Mayor + 64 conseillers across 19 boroughs) | **Next election:** 2025-11-02 (most recent)

**Status snapshot (2026-05-05):** 🚧 **Research only.** Roster live (5 rows; full council ingest pending). **The strongest municipal-Hansard-equivalent source in Canada lives here** — the `donnees.montreal.ca` CKAN portal publishes per-meeting closed-caption ZIPs of the live council webcast (real-time stenography, 2018 onward). Treat Montréal as the **municipal reference implementation** when the workstream is promoted, on the same logic that NS was the provincial reference.

---

## Bills / Règlements

- **Source URL(s):** https://ville.montreal.qc.ca/sel/sypre-consultation/ (GDD — *Gestion des dossiers décisionnels*, 520 on probe with bot UA); https://donnees.montreal.ca/dataset/?q=reglement (CKAN search)
- **Format:** GDD is the canonical decisions-tracking system; CKAN republishes structured slices.
- **Difficulty (1-5):** **3** via CKAN once the right dataset is identified; GDD direct is fronted by something that 520'd on probe.
- **Notes:** Montréal's regulatory output is bilingual (FR primary, EN translations not always 1:1). Schema implication: `bills.title` and `bills.title_en` separate fields, or a single field with FR primary and a `_translations` JSONB sidecar.

## Hansard — *Sous-titrage du conseil municipal* ★

- **Source:** https://donnees.montreal.ca/dataset/sous-titrage-conseil-municipal (CKAN dataset id: package_show api → `sous-titrage-conseil-municipal`)
- **Format:** **ZIP file per séance**, contents are the real-time captions produced by the city's stenography service during the live webcast. 2018-onward archive confirmed (probe 2026-05-05 returned dated resources for 2018-02 through 2018-08 in the first six rows — full extent likely 2018+ to current).
- **Granularity:** Per-meeting; within the file, line-by-line timestamped caption text. **Speaker identification: variable** — captions use stenographer-assigned speaker tags (e.g. "M. LE MAIRE :"), but consistency depends on the steno service of the day.
- **Difficulty (1-5):** **2** (CKAN download, ZIP/text parse).
- **Caveat in the dataset's own avertissement:**

  > Les fichiers de sous-titrage ne sont pas un compte rendu écrit fournissant le mot à mot des échanges du conseil municipal. Ils sont plutôt des transcriptions en temps réel pour permettre la compréhension aux personnes ayant un handicap auditif. Aucune correction ou validation n'est faite après la diffusion.

  Translation: captions are real-time accessibility transcription, NOT a verified verbatim record. For semantic-search this is acceptable (the schema can carry `speech_quality='realtime_caption'` to flag the lower fidelity); for direct quotation in a report, footnote the source as captions-not-Hansard.

- **Speaker identification:** Per-line tags exist but aren't programmatic IDs; resolution to `politicians.id` is **name-fuzz against the council roster** + role-based fallback (M. LE MAIRE = Valérie Plante / current mayor at the time). Same pattern as the legacy NS pre-slug attribution.

## Voting Records

- **Source URL(s):** Decision data on GDD; some republished on CKAN (`package_search?q=conseil+municipal` returned `contrats-conseil-municipal-et-conseil-d-agglomeration` among others).
- **Format:** Per-decision recorded-vote table where applicable. Many decisions are by voice / consensus.
- **Difficulty (1-5):** **3** — needs targeted CKAN dataset enumeration.

## Committee / Comité exécutif

- Note Montréal's structure: **conseil municipal** (full council, ~65 seats) + **conseil d'agglomération** (regional council overlapping the island) + **comité exécutif** (mayor's cabinet). Each produces its own decisions and votes. Schema needs to accommodate the comité-exécutif as a distinct decision body — it's not a standing committee in the Toronto sense.
- CKAN `package_search?q=conseil+municipal` returned datasets that bundle conseil-municipal + conseil-d'agglomération in the same row set (e.g. the contracts dataset). Disambiguating which body decided each item will need a column or filter at ingest.

## Open-data CKAN — recommended path

- Portal: https://donnees.montreal.ca/
- CKAN API base: `https://donnees.montreal.ca/api/3/action/`
- Probe of `package_search?q=conseil+municipal` → **16 datasets**, including:
  - `sous-titrage-conseil-municipal` (★ captions archive — see Hansard above)
  - `calendrier-seances-comite-executif-conseil-municipal-conseil-agglomeration` (meeting calendar — exec / council / agglomération)
  - `profils-participants-questions-conseil-municipal` (public-question participant profiles — accountability surface)
  - `contrats-conseil-municipal-et-conseil-d-agglomeration` (contracts approved by decision)
  - `subventions-conseil-de-ville-et-d-agglomeration` (subsidies)
  - 11 more
- CKAN backend hosted by `istio-envoy / google` (probe response: `via: 1.1 google`), 24h cache, no observed rate-limit issue.

## Terms / Licensing

- Montréal open data is published under **Creative Commons CC-BY 4.0** for most datasets — permissive, attribution required, redistribution allowed including commercially. Confirm per-dataset on the resource page.
- The captions dataset's avertissement does not restrict redistribution; the *quality* caveat is what travels with the data.

## Rate limits / auth

- CKAN endpoint: no documented per-IP limit; default `Cache-Control: public, max-age=86400`. Daily-cache-friendly.
- Caption ZIPs are large (each meeting ~hundreds of KB to a few MB); prefer downloading individual resources rather than the whole package at once.

## Open questions (for the user before any code)

1. Is Montréal an acceptable choice for the *first* municipal speech ingest? It's the only city in tier-1 with a verbatim-quality (caveat: real-time) transcript surface on day one, and its bilingual nature exercises the same FR/EN seams that the QC pipeline already deals with.
2. Are we comfortable carrying captions as the speech corpus, with a `speech_quality='realtime_caption'` flag, given the avertissement that no post-broadcast correction is performed?
3. How should the **comité exécutif** show up in the model? Standing committee, separate body, or third tier of municipal decision-making?

## Status checklist

- [x] System fingerprint (CKAN ★ captions + GDD) — 2026-05-05
- [x] Captions dataset confirmed live with 2018+ archive — 2026-05-05
- [ ] Full CKAN dataset enumeration (bylaws, votes, committees, comité exécutif)
- [ ] Sample caption-ZIP download + parse to confirm timestamp / speaker-tag format
- [ ] Decision on captions-as-speeches schema (`speech_quality` field, retention of original text)
- [ ] User research-handoff: any contacts at Ville de Montréal Open Data team
- [ ] Schema-design session: bilingual fields, comité exécutif body, agglomération vs municipal council
- [ ] First scraper module (post-handoff)
