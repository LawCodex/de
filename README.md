# LawCodex — Germany (`de`)

German **federal law (Bundesrecht)** in force, as plain Markdown — one file per law, in the
original German. Generated from the official consolidated XML published by the Federal Ministry
of Justice (BMJ) and juris GmbH on [gesetze-im-internet.de](https://www.gesetze-im-internet.de/).

Retrieved: **2026-10-11** (each file's front matter has its own `retrieved` and `consolidated` dates).

## Coverage

Every entry of the official index [`gii-toc.xml`](https://www.gesetze-im-internet.de/gii-toc.xml)
— **6,139 documents**, all converted (0 download or conversion failures):

| Directory | Contents | Files |
| --- | --- | ---: |
| `grundgesetz/` | Grundgesetz für die Bundesrepublik Deutschland (GG) | 1 |
| `gesetze/` | Federal statutes (Gesetze, Gesetzbücher, and statutes named *-ordnung* such as ZPO, StPO, AO, InsO, GewO, BRAO) | 1,826 |
| `verordnungen/` | Federal ordinances (Rechtsverordnungen, incl. *-ordnung* ordinances such as StVO, StVZO, Approbations-/Wahlordnungen) | 2,934 |
| `sonstige/` | Other instruments published on gesetze-im-internet.de | 1,378 |
| **Total** | | **6,139** |

Breakdown of `sonstige/` by front-matter `type`: 873 `notice` (Bekanntmachungen),
306 `order` (Anordnungen), 62 `decree` (Erlasse, e.g. Organisationserlasse), 49 `treaty`
(Abkommen/Verträge published as such), 6 `rules_of_procedure` (Geschäftsordnungen), 82 `other`
(Satzungen, Richtlinien, plans, Bundestag house rules etc.).

Machine-readable counts: [`scripts/stats.json`](scripts/stats.json).

### Not covered

- **State law (Landesrecht)** of the 16 Länder — not on gesetze-im-internet.de; each Land runs its
  own portal (e.g. gesetze-bayern.de, recht.nrw.de, landesrecht-bw.de) with different formats
  and no common bulk export. Out of scope for now.
- **Historical versions / amending acts as promulgated** — only the current consolidated text
  is provided by the source. The promulgated Bundesgesetzblatt is at
  [recht.bund.de](https://www.recht.bund.de/).
- **Administrative regulations** (Verwaltungsvorschriften, at
  verwaltungsvorschriften-im-internet.de), court decisions, and EU law.
- **English translations** offered for some laws on gesetze-im-internet.de (non-authoritative).
- **Images and PDF attachments** (formulas, forms, maps — about 4,150 references) are not copied
  into the repo; they are linked to the official files under
  `https://www.gesetze-im-internet.de/normengrafiken/…`.

## Structure

```
grundgesetz/gg.md
gesetze/<letter>/<slug>.md         e.g. gesetze/b/bgb.md, gesetze/s/stgb.md, gesetze/s/sgb-5.md
verordnungen/<letter>/<slug>.md    e.g. verordnungen/s/stvo-2013.md
sonstige/<letter>/<slug>.md
scripts/                           fetch + convert code
```

- `<slug>` is the official gesetze-im-internet.de path name (`https://www.gesetze-im-internet.de/<slug>/`),
  lowercased with `_` → `-`. It is stable and usually derived from the official abbreviation.
- Files are bucketed by the first character of the slug (`0-9/` for digits) so no directory
  exceeds GitHub's 1,000-entry listing limit.
- Inside each file: `#` = title; the law's own outline (Buch/Teil/Abschnitt/Titel/Kapitel…,
  from `gliederungskennzahl`) maps to `##`…; individual norms (`§ …`, `Art …`, `Anlage …`,
  Eingangsformel, Schlussformel) are headings one level below their enclosing unit, capped at
  `######` — deeper norms (e.g. in the BGB) are bold labels.
- Numbered/lettered enumerations become nested Markdown lists; simple tables become Markdown
  tables, complex ones (row/column spans, nested content) are kept as HTML. Footnotes are rendered
  as `<sup>n)</sup>` markers with the note text after the norm. Editorial notes from the source
  (e.g. `(+++ Textnachweis … +++)`) are rendered as block quotes.

Front matter example:

```yaml
title: "Strafgesetzbuch"
abbreviation: "StGB"
identifier: "BJNR001270871"      # juris document number
type: act                        # constitution | act | ordinance | notice | order | decree | treaty | rules_of_procedure | other
jurisdiction: de
language: de
date: 1871-05-15                 # Ausfertigungsdatum
last_amended: 2026-03-20         # date of the last amending act (from the "Stand" note)
consolidated: 2026-09-28         # build date of the source XML
status: in_force
citation: ["RGBl 1871, 127"]
stand: ["Neuf: Neugefasst durch Bek. v. 13.11.1998 I 3322;", "Stand: zuletzt geändert durch Art. 1 G v. 20.3.2026 I Nr. 95"]
source: "https://www.gesetze-im-internet.de/stgb/"
retrieved: 2026-10-11
```

`status` is `in_force` for all files because gesetze-im-internet.de only lists current law;
scheduled expiry is visible in `stand` entries of type `Aufh:`.

### Classification caveat

The source XML does not state whether a document is a statute or an ordinance. The category is
derived (see `classify()` in `scripts/convert.py`) from the head noun of the official title
(…gesetz → Gesetz, …verordnung → Verordnung, Bekanntmachung/Anordnung/Erlass… → sonstige), with the
enacting formula (Eingangsformel: "verordnet" vs. "hat … das folgende Gesetz beschlossen") deciding
ambiguous *-ordnung* titles, plus a short list of statutes named *-ordnung*. A small number of
edge cases may be misfiled; the text itself is unaffected.

## Sources

- **gesetze-im-internet.de** (BMJ / Bundesamt für Justiz, with juris GmbH) — official
  consolidated federal law. Index: <https://www.gesetze-im-internet.de/gii-toc.xml>; each law as
  `https://www.gesetze-im-internet.de/<slug>/xml.zip` (DTD:
  <https://www.gesetze-im-internet.de/dtd/1.01/gii-norm.dtd>).
- Evaluated but not used: **NeuRIS / Rechtsinformationsportal des Bundes**
  (<https://testphase.rechtsinformationen.bund.de/>, API `/v1/legislation`). It offers LegalDocML.de
  XML/HTML with ELI identifiers, but is still a test phase and listed 5,495 items on the retrieval
  date versus 6,139 on gesetze-im-internet.de. It may replace the source once complete.

## Licence / copyright

Statutes, ordinances, official notices and other official works are not protected by copyright
in Germany (**§ 5 Abs. 1 UrhG**, "amtliche Werke"). The texts here are reproduced unchanged from
the official source; only the formatting was converted. Note that the consolidated texts on
gesetze-im-internet.de are an official service but not the legally binding promulgation, which
is the Bundesgesetzblatt / Bundesanzeiger. The conversion scripts in `scripts/` may be reused freely.

## Regenerate

```sh
python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt
.venv/bin/python scripts/fetch.py   ../_raw/de      # downloads gii-toc.xml + ~6,100 xml.zip (~320 MB), cached
.venv/bin/python scripts/convert.py ../_raw/de .    # rewrites grundgesetz/ gesetze/ verordnungen/ sonstige/
```

`fetch.py` uses a descriptive User-Agent, 4 parallel connections, retries with backoff, and skips
already-downloaded zips (`--refresh` to re-download). `convert.py --only <slug> …` converts
selected laws only. Delete the raw directory afterwards.
