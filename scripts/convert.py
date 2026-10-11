#!/usr/bin/env python3
"""Convert gesetze-im-internet.de XML (gii-norm DTD) to LawCodex Markdown.

Usage: convert.py [RAW_DIR] [OUT_DIR]
  RAW_DIR  directory filled by fetch.py (contains gii-toc.xml and zip/)
  OUT_DIR  repository root (default: parent of scripts/)

Output: grundgesetz/gg.md and gesetze/, verordnungen/, sonstige/ — one
<first-letter>/<slug>.md per law (bucketed to stay under 1,000 entries per directory),
plus scripts/stats.json with counts per category.
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from lxml import etree

BASE = "https://www.gesetze-im-internet.de"

# --------------------------------------------------------------------------- text helpers

def esc(s):
    """Escape Markdown-significant characters in source text."""
    s = s.replace("\\", "\\\\")
    s = s.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    return s


LINE_START = re.compile(r"^(\d+)([.)])(\s|$)")
LINE_START2 = re.compile(r"^([#+=\-|~])")


def esc_line_start(line):
    m = LINE_START.match(line)
    if m:
        return m.group(1) + "\\" + line[len(m.group(1)):]
    if LINE_START2.match(line):
        return "\\" + line
    return line


def ws(s):
    return re.sub(r"[ \t\r\f\v ]+", lambda m: " " if " " not in m.group(0) else " ", s)


def text_of(e):
    return "".join(e.itertext()) if e is not None else ""


# --------------------------------------------------------------------------- renderer

class Renderer:
    BLOCK = {"DL", "table", "P", "pre", "TOC", "Revision", "Content", "Footnotes",
             "Title", "Subtitle", "Ident", "AttArea"}

    def __init__(self, slug):
        self.slug = slug
        self.footnotes = {}  # ID -> label

    def url(self, src):
        """Images/PDF attachments are served from /normengrafiken/<dir>/<file>."""
        src = src or ""
        m = re.match(r"^([A-Za-z]+\d*_\d{4})_(.+)$", src)
        if m:
            return f"{BASE}/normengrafiken/{m.group(1)}/{m.group(2)}"
        if "_" in src:
            a, b = src.split("_", 1)
            return f"{BASE}/normengrafiken/{a}/{b}"
        return f"{BASE}/{self.slug}/{src}"

    # ---- inline markdown
    def inline(self, e):
        """Inline Markdown for an element's content (BR -> '\n')."""
        out = []
        if e.text:
            out.append(esc(ws(e.text)))
        for c in e:
            out.append(self.inline_el(c))
            if c.tail:
                out.append(esc(ws(c.tail)))
        return "".join(out)

    def inline_el(self, c):
        t = c.tag
        if not isinstance(t, str):
            return ""
        if t == "BR":
            return "\n"
        if t in ("B", "I"):
            inner = self.inline(c)
            if not inner.strip() or "\n" in inner:
                return inner
            mark = "**" if t == "B" else "*"
            lead = inner[: len(inner) - len(inner.lstrip())]
            trail = inner[len(inner.rstrip()):]
            return f"{lead}{mark}{inner.strip()}{mark}{trail}"
        if t in ("SUP", "SUB"):
            inner = self.inline(c)
            return f"<{t.lower()}>{inner}</{t.lower()}>" if inner.strip() else inner
        if t == "FnR":
            lab = self.footnotes.get(c.get("ID"), "*")
            return f"<sup>{esc(lab)}</sup>"
        if t == "IMG":
            alt = (c.get("title") or c.get("alt") or "Bild").replace("]", ")").replace("[", "(")
            return f"![{esc(alt)}]({self.url(c.get('SRC'))})"
        if t == "FILE":
            tt = c.get("SRC")
            return f"[{esc(tt)}]({self.url(tt)})"
        if t == "Split":
            return " … "
        if t in ("ABWFORMAT", "AttR", "AttArea", "Accolade"):
            return ""
        if t == "QuoteL":
            return "„"
        if t == "QuoteR":
            return "“"
        if t == "FnArea":
            return "".join(self.inline_el(x) for x in c)
        if t in self.BLOCK:
            # block inside inline context (e.g. table inside entry) -> flatten
            return "\n" + "\n\n".join(self.blocks(c)) + "\n"
        # U, SP, small, F, NB, noindex, Citation, kommentar, LA, DT ... -> content
        return self.inline(c)

    # ---- blocks: return list of block strings (each may span lines)
    def para(self, s):
        """Turn inline text (with \n line breaks) into zero or more paragraph blocks."""
        s = s.replace("\r", "")
        paras = re.split(r"\n\s*\n", s)
        res = []
        for p in paras:
            lines = [ln.strip() for ln in p.split("\n")]
            lines = [ln for ln in lines if ln]
            if not lines:
                continue
            lines = [esc_line_start(ln) for ln in lines]
            res.append("\\\n".join(lines))
        return res

    def blocks(self, e):
        """Render mixed content of e as a list of Markdown blocks."""
        res = []
        buf = []
        self._walk(e, res, buf)
        if buf:
            res.extend(self.para("".join(buf)))
        return res

    BLOCKY = {"DL", "table", "P", "pre", "TOC", "Footnotes", "Content", "Revision", "LA", "DD"}

    def _walk(self, e, res, buf):
        def flush():
            if buf:
                res.extend(self.para("".join(buf)))
                buf.clear()

        if e.text:
            buf.append(esc(ws(e.text)))
        for c in e:
            t = c.tag if isinstance(c.tag, str) else None
            if t == "DL":
                flush()
                res.extend(self.dl(c))
            elif t == "table":
                flush()
                res.extend(self.table(c))
            elif t in ("P", "Content", "Revision", "LA", "DD", "fussnoten", "text"):
                flush()
                self._walk(c, res, buf)
                flush()
            elif t == "pre":
                flush()
                res.extend(self.para(self.inline(c)))
            elif t == "TOC":
                flush()
                res.extend(self.toc(c))
            elif t == "Footnotes":
                flush()
                res.extend(self.footnote_list(c))
            elif t in ("Title", "Subtitle", "Ident"):
                flush()
                txt = self.inline(c).strip()
                if txt:
                    res.extend(self.para(f"**{txt}**" if "\n" not in txt else txt))
            elif t is not None and t not in ("B", "I", "SUP", "SUB") and any(
                    isinstance(x.tag, str) and x.tag in self.BLOCKY for x in c.iterdescendants()):
                # transparent wrapper (noindex, small, SP, U, kommentar...) around block content
                self._walk(c, res, buf)
            elif t is not None:
                buf.append(self.inline_el(c))
            if c.tail:
                buf.append(esc(ws(c.tail)))

    def dl(self, e):
        items = []
        kids = [c for c in e if isinstance(c.tag, str)]
        label = None
        for c in kids:
            if c.tag == "DT":
                label = re.sub(r"\s+", " ", self.inline(c)).strip()
            elif c.tag == "DD":
                body = self.blocks(c)
                items.append(self.list_item(label or "", body))
                label = None
        if label:
            items.append(self.list_item(label, []))
        return ["\n".join(items)] if items else []

    @staticmethod
    def list_item(label, body):
        first = esc_line_start(label) if label else ""
        lines = []
        body_lines = "\n\n".join(body).split("\n") if body else []
        if body_lines:
            head = body_lines[0]
            if first:
                # body's first line may start with an escaped list marker; that's fine mid-line
                head = (first + " " + head) if head else first
            lines.append("- " + head)
            for ln in body_lines[1:]:
                lines.append(("  " + ln) if ln else "")
        else:
            lines.append("- " + (first or " "))
        return "\n".join(lines)

    def footnote_list(self, e):
        res = []
        for fn in e:
            if not isinstance(fn.tag, str) or fn.tag != "Footnote":
                continue
            lab = self.footnotes.get(fn.get("ID")) or (fn.get("FnZ") or "*") + (fn.get("Postfix") or "")
            body = self.blocks(fn)
            text = "\n\n".join(body)
            res.append(f"<sup>{esc(lab)}</sup> " + text)
        return res

    def toc(self, e):
        lines = []
        cur = ""
        res = []
        for c in e:
            if not isinstance(c.tag, str):
                continue
            if c.tag == "Ident":
                if cur:
                    lines.append(cur)
                cur = re.sub(r"\s+", " ", self.inline(c)).strip()
            elif c.tag in ("Title", "Subtitle"):
                t = re.sub(r"\s+", " ", self.inline(c)).strip()
                cur = (cur + " " + t).strip() if cur else t
                lines.append(cur)
                cur = ""
            else:
                if cur:
                    lines.append(cur)
                    cur = ""
                if lines:
                    res.append("\\\n".join(esc_line_start(x) for x in lines if x))
                    lines = []
                res.extend(self.blocks(c) if c.tag != "table" else self.table(c))
        if cur:
            lines.append(cur)
        if lines:
            res.append("\\\n".join(esc_line_start(x) for x in lines if x))
        return res

    # ---- tables
    def table(self, e):
        res = []
        title = e.find("Title")
        if title is not None:
            t = re.sub(r"\s+", " ", self.inline(title)).strip()
            if t:
                res.append(f"**{t}**")
        for tg in e.findall("tgroup"):
            res.append(self.tgroup(tg))
        return [r for r in res if r]

    def tgroup(self, tg):
        cols = [c.get("colname") for c in tg.findall("colspec")]
        try:
            ncols = int(tg.get("cols") or len(cols) or 1)
        except ValueError:
            ncols = len(cols) or 1
        if len(cols) < ncols:
            cols += [f"__c{i}" for i in range(len(cols), ncols)]
        colidx = {c: i for i, c in enumerate(cols) if c}
        head = tg.find("thead")
        body = tg.find("tbody")
        foot = tg.find("tfoot")
        hrows = head.findall("row") if head is not None else []
        brows = (body.findall("row") if body is not None else []) + (foot.findall("row") if foot is not None else [])
        simple = len(hrows) <= 1
        for r in hrows + brows:
            for en in r.findall("entry"):
                if en.get("namest") or en.get("morerows") or en.get("spanname"):
                    simple = False
                if any(isinstance(x.tag, str) and x.tag in ("DL", "table", "P", "pre", "TOC") for x in en.iter()):
                    simple = False
            if len(r.findall("entry")) > ncols:
                simple = False
        if simple:
            return self.md_table(hrows, brows, ncols, colidx)
        return self.html_table(hrows, brows, colidx)

    def cell_md(self, en):
        s = self.inline(en)
        s = re.sub(r"[ \t]*\n[ \t]*", "<br>", s.strip())
        s = re.sub(r"(<br>)+$", "", s)
        return s.replace("|", "\\|")

    def md_row(self, row, ncols, colidx):
        cells = [""] * ncols
        pos = 0
        for en in row.findall("entry"):
            cn = en.get("colname")
            if cn in colidx:
                pos = colidx[cn]
            if pos < ncols:
                cells[pos] = self.cell_md(en)
            pos += 1
        return "| " + " | ".join(cells) + " |"

    def md_table(self, hrows, brows, ncols, colidx):
        lines = []
        if hrows:
            lines.append(self.md_row(hrows[0], ncols, colidx))
        else:
            lines.append("|" + " |" * ncols)
        lines.append("|" + " --- |" * ncols)
        for r in brows:
            lines.append(self.md_row(r, ncols, colidx))
        return "\n".join(lines)

    def html_table(self, hrows, brows, colidx):
        out = ["<table>"]

        def rows(rs, tag):
            for r in rs:
                cells = []
                for en in r.findall("entry"):
                    attrs = ""
                    st, nd = en.get("namest"), en.get("nameend")
                    if st in colidx and nd in colidx and colidx[nd] > colidx[st]:
                        attrs += f' colspan="{colidx[nd] - colidx[st] + 1}"'
                    mr = en.get("morerows")
                    if mr and mr.isdigit() and int(mr) > 0:
                        attrs += f' rowspan="{int(mr) + 1}"'
                    cells.append(f"<{tag}{attrs}>{self.html_inline(en).strip()}</{tag}>")
                out.append("<tr>" + "".join(cells) + "</tr>")

        if hrows:
            out.append("<thead>")
            rows(hrows, "th")
            out.append("</thead>")
        out.append("<tbody>")
        rows(brows, "td")
        out.append("</tbody>")
        out.append("</table>")
        return "\n".join(out)

    def html_inline(self, e):
        out = []
        if e.text:
            out.append(html.escape(ws(e.text), quote=False))
        for c in e:
            out.append(self.html_el(c))
            if c.tail:
                out.append(html.escape(ws(c.tail), quote=False))
        s = "".join(out)
        return s.replace("\n", " ")

    def html_el(self, c):
        t = c.tag
        if not isinstance(t, str):
            return ""
        if t == "BR":
            return "<br>"
        if t in ("B", "I", "SUP", "SUB"):
            tag = {"B": "b", "I": "i", "SUP": "sup", "SUB": "sub"}[t]
            return f"<{tag}>{self.html_inline(c)}</{tag}>"
        if t == "FnR":
            return f"<sup>{html.escape(self.footnotes.get(c.get('ID'), '*'))}</sup>"
        if t == "IMG":
            alt = html.escape(c.get("title") or c.get("alt") or "Bild")
            return f'<img src="{self.url(c.get("SRC"))}" alt="{alt}">'
        if t == "FILE":
            src = c.get("SRC")
            return f'<a href="{self.url(src)}">{html.escape(src)}</a>'
        if t == "Split":
            return " … "
        if t in ("ABWFORMAT", "AttR", "AttArea", "Accolade"):
            return ""
        if t == "DL":
            parts = []
            label = ""
            for x in c:
                if not isinstance(x.tag, str):
                    continue
                if x.tag == "DT":
                    label = self.html_inline(x).strip()
                elif x.tag == "DD":
                    parts.append(f"<li>{label} {self.html_inline(x).strip()}</li>")
                    label = ""
            return "<ul>" + "".join(parts) + "</ul>"
        if t == "table":
            res = []
            title = c.find("Title")
            if title is not None:
                res.append(f"<b>{self.html_inline(title)}</b>")
            for tg in c.findall("tgroup"):
                cols = [x.get("colname") for x in tg.findall("colspec")]
                colidx = {cc: i for i, cc in enumerate(cols) if cc}
                head, body, foot = tg.find("thead"), tg.find("tbody"), tg.find("tfoot")
                hrows = head.findall("row") if head is not None else []
                brows = (body.findall("row") if body is not None else []) + (foot.findall("row") if foot is not None else [])
                res.append(self.html_table(hrows, brows, colidx).replace("\n", ""))
            return "".join(res)
        if t in ("P", "LA", "DD", "Content", "Revision", "pre", "Title", "Subtitle", "Ident"):
            inner = self.html_inline(c).strip()
            return (inner + "<br>") if inner else ""
        if t == "QuoteL":
            return "„"
        if t == "QuoteR":
            return "“"
        return self.html_inline(c)


# --------------------------------------------------------------------------- classification

LAW_ORDNUNG = {
    "ZPO", "StPO", "AO", "InsO", "GewO", "HwO", "BNotO", "BRAO", "VwGO", "FGO", "GBO",
    "WBO", "WDO", "PAO", "BHO", "WiPrO", "BÄO", "BTÄO", "BApO", "SchRegO", "RVO",
    "PatAnwO", "SchO", "BDO", "KO", "VglO", "SeemO", "BWahlG", "ZahnHkG",
}

WORD_RULES = [
    (re.compile(r"(gesetz|gesetzbuch|gesetzes)$"), "gesetz"),
    (re.compile(r"verordnung$"), "verordnung"),
    (re.compile(r"(anordnung|geschäftsordnung|dienstordnung|benutzungsordnung|hausordnung|geheimschutzordnung)$"), "sonstige"),
    (re.compile(r"ordnung$"), "ordnung"),
    (re.compile(r"(abkommen|vertrag|übereinkommen|protokoll|vereinbarung|notenwechsel|konvention|charta|statut)$"), "vertrag"),
    (re.compile(r"(bekanntmachung|erlass|erlaß|satzung|richtlinie|richtlinien|verwaltungsvorschrift|beschluss|beschluß|bestimmungen|regelung|regelungen|grundsätze|verfügung|vorschriften|tarif|plan|raumordnungsplan|entscheidung|anweisung|festsetzung)$"), "sonstige"),
]


def eingang_signal(e):
    e = (e or "").lower()
    if re.search(r"\bverordne[tn]\b", e):
        return "verordnung"
    if re.search(r"(bundestag|bundesrat)[^.]{0,200}(das folgende gesetz|gesetz beschlossen)", e):
        return "gesetz"
    return None


def classify(meta, eingang):
    jurabk = meta.get("jurabk", "")
    if jurabk == "GG":
        return "grundgesetz"
    if meta.get("amtabk") in LAW_ORDNUNG or jurabk in LAW_ORDNUNG:
        return "gesetz"
    sig = eingang_signal(eingang)
    for t in (meta.get("langue"), meta.get("kurzue")):
        if not t:
            continue
        head = re.split(r"\s[(–]|\s-\s|\s\*\)", t, maxsplit=1)[0]
        words = re.findall(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß-]*", head)
        for w in words:
            lw = w.strip("-").split("-")[-1].lower()
            if not lw:
                continue
            for rx, cat in WORD_RULES:
                if rx.search(lw):
                    if cat == "ordnung":
                        return sig or "verordnung"
                    return cat
    if sig:
        return sig
    if re.search(r"(V|VO|AnO)(\s|$|\d)", jurabk):
        return "verordnung"
    if re.search(r"G(\s|$|\d)", jurabk):
        return "gesetz"
    return "sonstige"


CAT_DIR = {"grundgesetz": "grundgesetz", "gesetz": "gesetze", "verordnung": "verordnungen",
           "vertrag": "sonstige", "sonstige": "sonstige"}
CAT_TYPE = {"grundgesetz": "constitution", "gesetz": "act", "verordnung": "ordinance",
            "vertrag": "treaty", "sonstige": "other"}


# --------------------------------------------------------------------------- conversion

STRUCT_ANNEX = re.compile(r"^(Anlage|Anlagen|Anhang|Schlu(ss|ß)formel|Muster)\b")
DATE_DMY = re.compile(r"v(?:om)?\.\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})")


def parse_meta(norm, r):
    md = norm.find("metadaten")
    m = {}
    for k in ("jurabk", "amtabk", "ausfertigung-datum", "enbez"):
        v = md.findtext(k)
        if v:
            m[k] = v.strip()
    for k in ("kurzue", "langue", "titel"):
        x = md.find(k)
        if x is not None:
            v = re.sub(r"\s+", " ", text_of(x)).strip()
            if v:
                m[k] = v
    m["fundstellen"] = [
        f"{(f.findtext('periodikum') or '').strip()} {(f.findtext('zitstelle') or '').strip()}".strip()
        for f in md.findall("fundstelle")
    ]
    m["stand"] = [
        f"{(s.findtext('standtyp') or '').strip()}: {re.sub(r'\s+', ' ', text_of(s.find('standkommentar'))).strip()}"
        for s in md.findall("standangabe")
    ]
    return m


def yq(v):
    return json.dumps(v, ensure_ascii=False)


def convert_zip(zpath, slug, retrieved):
    zf = zipfile.ZipFile(zpath)
    xmls = sorted(n for n in zf.namelist() if n.lower().endswith(".xml"))
    norms = []
    for n in xmls:
        root = etree.fromstring(zf.read(n), etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True))
        norms.extend(root.findall("norm"))
    if not norms:
        return None
    r = Renderer(slug)
    # footnote labels
    for fn in (x for nm in norms for x in nm.iter("Footnote")):
        r.footnotes[fn.get("ID")] = (fn.get("FnZ") or "*") + (fn.get("Postfix") or "")

    head = parse_meta(norms[0], r)
    doknr = norms[0].get("doknr")
    eingang = ""
    for nm in norms[:6]:
        en = nm.findtext("metadaten/enbez") or ""
        if en.startswith("Eingangsformel") or en == "(XXXX)":
            eingang += text_of(nm.find("textdaten/text"))
    if not eingang and len(norms) > 1:
        eingang = text_of(norms[1].find("textdaten/text"))[:1500]
    cat = classify(head, eingang)
    ctype = CAT_TYPE[cat]
    if cat == "sonstige":
        tl = (head.get("langue") or head.get("kurzue") or "").lower()
        for kw, ty in (("bekanntmachung", "notice"), ("anordnung", "order"), ("erlass", "decree"),
                       ("erlaß", "decree"), ("geschäftsordnung", "rules_of_procedure")):
            if kw in tl.split(" ")[0] or (kw in tl[:60] and ty == "notice" and tl.split(" ")[0].endswith("e")):
                ctype = ty
                break

    title = head.get("langue") or head.get("kurzue") or head.get("jurabk")
    abbr = head.get("amtabk") or head.get("jurabk")
    last = None
    for s in head["stand"]:
        if s.startswith("Stand:") or s.startswith("Neuf:"):
            mm = DATE_DMY.search(s)
            if mm:
                d = dt.date(int(mm.group(3)), int(mm.group(2)), int(mm.group(1)))
                if last is None or d > last:
                    last = d
    build = norms[0].get("builddate") or ""

    fm = ["---", f"title: {yq(title)}"]
    if head.get("kurzue") and head.get("kurzue") != title:
        fm.append(f"short_title: {yq(head['kurzue'])}")
    if abbr:
        fm.append(f"abbreviation: {yq(abbr)}")
    fm.append(f"identifier: {yq(doknr)}")
    fm.append(f"type: {ctype}")
    fm.append("jurisdiction: de")
    fm.append("language: de")
    if head.get("ausfertigung-datum") and re.match(r"^\d{4}-\d{2}-\d{2}$", head["ausfertigung-datum"]):
        fm.append(f"date: {head['ausfertigung-datum']}")
    if last:
        fm.append(f"last_amended: {last.isoformat()}")
    if re.match(r"^\d{8}", build):
        fm.append(f"consolidated: {build[:4]}-{build[4:6]}-{build[6:8]}")
    fm.append("status: in_force")
    if head["fundstellen"]:
        fm.append("citation:")
        fm += [f"  - {yq(f)}" for f in head["fundstellen"] if f]
    if head["stand"]:
        fm.append("stand:")
        fm += [f"  - {yq(s)}" for s in head["stand"]]
    fm.append(f"source: {yq(BASE + '/' + slug + '/')}")
    fm.append(f"retrieved: {retrieved}")
    fm.append("---")

    out = ["\n".join(fm), "# " + esc(title)]
    depth = 0
    struct_title = ""
    for i, nm in enumerate(norms):
        md = nm.find("metadaten")
        td = nm.find("textdaten")
        blocks = []
        if i > 0:
            ge = md.find("gliederungseinheit")
            enbez = (md.findtext("enbez") or "").strip()
            if enbez == "(XXXX)" or enbez.startswith("(XXXX)"):
                enbez = enbez[6:].strip()
            tit = md.find("titel")
            titel = re.sub(r"\s+", " ", r.inline(tit)).strip() if tit is not None else ""
            if ge is not None:
                kz = (ge.findtext("gliederungskennzahl") or "").strip()
                level = max(1, len(kz) // 3)
                bez = (ge.findtext("gliederungsbez") or "").strip()
                gt = ge.find("gliederungstitel")
                gtit = re.sub(r"\s+", " ", r.inline(gt)).strip() if gt is not None else ""
                htxt = " — ".join(x for x in (esc(bez), gtit) if x)
                depth = level
                struct_title = bez + " " + text_of(gt)
                if htxt:
                    blocks.append(heading(1 + level, htxt))
            elif enbez or titel:
                if STRUCT_ANNEX.match(enbez) and not re.search(r"Anl|Anh|Schlu", struct_title):
                    depth = 0
                htxt = " ".join(x for x in (esc(enbez), titel) if x)
                blocks.append(heading(2 + depth, htxt))
        if td is not None:
            t = td.find("text")
            if t is not None:
                blocks.extend(r.blocks(t))
            fn = td.find("fussnoten")
            if fn is not None:
                fb = r.blocks(fn)
                if fb:
                    blocks.append(blockquote(fb))
        out.extend(b for b in blocks if b and b.strip())
    md_text = "\n\n".join(out).rstrip() + "\n"
    md_text = re.sub(r"\n{3,}", "\n\n", md_text)
    return cat, md_text, head, ctype


def heading(level, text):
    text = text.replace("\n", " ").strip()
    if level <= 6:
        return "#" * level + " " + text
    return f"**{text}**"


def blockquote(blocks):
    txt = "\n\n".join(blocks)
    return "\n".join(("> " + ln) if ln else ">" for ln in txt.split("\n"))


def slugify(s):
    s = s.lower().replace("_", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:100] or "x"


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", nargs="?", default=str(here.parent.parent / "_raw" / "de"))
    ap.add_argument("out", nargs="?", default=str(here.parent))
    ap.add_argument("--only", nargs="*", help="only these GII slugs")
    args = ap.parse_args()
    raw, out = Path(args.raw), Path(args.out)

    toc = etree.parse(str(raw / "gii-toc.xml"))
    slugs = []
    for it in toc.iter("item"):
        slugs.append(urlparse(it.findtext("link").strip()).path.strip("/").split("/")[0])
    if args.only:
        slugs = [s for s in slugs if s in set(args.only)]

    if not args.only:
        for d in set(CAT_DIR.values()):
            for f in (out / d).rglob("*.md"):
                f.unlink()
    counts = Counter()
    used = {}
    missing, errors = [], []
    for n, slug in enumerate(slugs, 1):
        z = raw / "zip" / f"{slug}.zip"
        if not z.exists():
            missing.append(slug)
            continue
        retrieved = dt.date.fromtimestamp(z.stat().st_mtime).isoformat()
        try:
            res = convert_zip(z, slug, retrieved)
        except Exception as ex:  # keep going, report at end
            errors.append(f"{slug}: {ex!r}")
            continue
        if res is None:
            errors.append(f"{slug}: no norms")
            continue
        cat, text, head, ctype = res
        d = CAT_DIR[cat]
        name = slugify(slug)
        key = (d, name)
        if key in used:
            name = f"{name}-{slugify(head.get('jurabk', ''))}"
        used[(d, name)] = slug
        sub = out / d
        if d != "grundgesetz":
            # GitHub's web UI lists at most 1,000 entries per directory -> bucket by first character
            sub = sub / (name[0] if name[0].isalpha() else "0-9")
        sub.mkdir(parents=True, exist_ok=True)
        (sub / f"{name}.md").write_text(text, encoding="utf-8", newline="\n")
        counts[d] += 1
        counts["type:" + ctype] += 1
        if n % 500 == 0:
            print(f"  {n}/{len(slugs)}", file=sys.stderr)
    stats = {"toc_entries": len(slugs), "counts": dict(sorted(counts.items())),
             "missing": missing, "errors": errors}
    if not args.only:
        (here / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
