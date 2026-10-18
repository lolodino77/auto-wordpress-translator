"""Règles éditoriales appliquées de façon déterministe au HTML traduit.

Source : spec/« Règles de rédaction des articles » et spec/« Guide de rédaction des références
bibliographiques ». Les règles sémantiques (église/Église, italique des mots étrangers, format des
références, etc.) sont imposées au LLM par le prompt ; ici on corrige et on contrôle ce qui peut l'être
mécaniquement. Chaque correction est consignée dans Report.fixes, chaque doute dans Report.warnings.
"""
import html as htmllib
import re
from dataclasses import dataclass, field

import bible

NBSP = " "
_TAG = re.compile(r"(<[^>]+>)")
_BLOCK_TAG = re.compile(r"</?(?:p|li|h[1-6]|blockquote|div|ul|ol|hr|br)\b", re.I)
_ENTITIES = {"&laquo;": "«", "&raquo;": "»", "&ldquo;": "“", "&rdquo;": "”", "&quot;": '"', "&#8220;": "“", "&#8221;": "”"}


@dataclass
class Report:
    fixes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_tag(token: str) -> bool:
    return token.startswith("<") and _TAG.fullmatch(token) is not None


def _map_text(html: str, fn) -> str:
    """Applique fn aux seuls morceaux de texte (jamais aux balises ni à leurs attributs)."""
    return "".join(p if _is_tag(p) else fn(p) for p in _TAG.split(html))


def _text_only(html: str) -> str:
    return htmllib.unescape(_TAG.sub(" ", html))


# --- 0. Balises autorisées seulement (le prompt n'en demande pas d'autres) --------------------------------
_ALLOWED = {"h3", "h4", "p", "ul", "ol", "li", "blockquote", "a", "em", "strong", "sup", "hr", "br",
            "h1", "h2", "h5", "h6"}  # h1/h2/h5/h6 : remappés ensuite par fix_headings
_SYNONYMS = {"i": "em", "b": "strong"}


def fix_tags(html: str, rep: Report) -> str:
    """Retire les balises non prévues (<mark>, <span>, <div>, <font>…) en gardant leur texte ; <i>→<em>, <b>→<strong>."""
    removed: set[str] = set()

    def sub(m: re.Match) -> str:
        slash, name = m.group(1), m.group(2).lower()
        if name in _SYNONYMS:
            return f"<{slash}{_SYNONYMS[name]}>"
        if name in _ALLOWED:
            return m.group(0)
        removed.add(name)
        return ""

    out = re.sub(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>", sub, html)
    if removed:
        rep.fixes.append("Balises HTML non prévues retirées : " + ", ".join(sorted(f"<{t}>" for t in removed)) + ".")
    return out


# --- 1. « Titres en H3, sous-titres en H4 » ---------------------------------------------------------
def fix_headings(html: str, rep: Report) -> str:
    levels = sorted({int(n) for n in re.findall(r"<h([1-6])\b", html, re.I)})
    if not levels:
        return html
    mapping = {lv: 3 if i == 0 else 4 for i, lv in enumerate(levels)}
    if len(levels) > 2:
        rep.warnings.append(f"{len(levels)} niveaux de titres dans la traduction : tous les niveaux sous le 2e sont mis en H4.")
    if any(lv != mapping[lv] for lv in levels):
        rep.fixes.append("Titres ramenés à H3 (titres) / H4 (sous-titres).")
    return re.sub(r"<(/?)h([1-6])\b", lambda m: f"<{m.group(1)}h{mapping[int(m.group(2))]}", html, flags=re.I)


# --- 2. « Écrire XXe et non XXème : XX<sup>e</sup> » -------------------------------------------------
_ROMAN = re.compile(r"M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})")
_ORDINAL = re.compile(r"\b([IVXLCDM]{2,}|\d{1,3})(ème|eme|e)\b")


def fix_ordinals(html: str, rep: Report) -> str:
    count = 0

    def sub(m: re.Match) -> str:
        nonlocal count
        num = m.group(1)
        if not num.isdigit() and not _ROMAN.fullmatch(num):
            return m.group(0)
        count += 1
        return f"{num}<sup>e</sup>"

    out = _map_text(html, lambda t: _ORDINAL.sub(sub, t))
    if count:
        rep.fixes.append(f"{count} nombre(s) ordinal(aux) mis en forme X<sup>e</sup>.")
    return out


# --- 3. Guillemets français « » (OQLF), espaces insécables à l'intérieur --------------------------
def _fix_block_quotes(tokens: list[str], rep: Report) -> list[str]:
    tokens = [re.sub("|".join(map(re.escape, _ENTITIES)), lambda m: _ENTITIES[m.group(0)], t) for t in tokens]
    depth = 0
    out = []
    for tok in tokens:  # guillemets anglais courbes “ ” -> « » (niveau 1) ; “ ” conservés pour une citation dans une citation
        buf = []
        for ch in tok:
            if ch == "“":
                buf.append("«" if depth == 0 else "“")
                depth += 1
            elif ch == "”":
                depth = max(depth - 1, 0)
                buf.append("»" if depth == 0 else "”")
            else:
                buf.append(ch)
        out.append("".join(buf))
    straight = sum(t.count('"') for t in out)
    if straight % 2:
        rep.warnings.append("Nombre impair de guillemets droits (\") dans un paragraphe : laissés tels quels, à corriger à la main.")
    elif straight:
        n = 0
        res = []
        for tok in out:
            parts = tok.split('"')
            built = parts[0]
            for p in parts[1:]:
                built += ("«" if n % 2 == 0 else "»") + p
                n += 1
            res.append(built)
        out = res
    return [re.sub(r"[  ]*»", NBSP + "»", re.sub(r"«[  " + NBSP + r"]*", "«" + NBSP, t)).replace(NBSP * 2, NBSP) for t in out]


def fix_quotes(html: str, rep: Report) -> str:
    result: list[str] = []
    block: list[int] = []  # indices (dans result) des morceaux de texte du paragraphe courant
    before = html

    def flush():
        if block:
            fixed = _fix_block_quotes([result[i] for i in block], rep)
            for i, t in zip(block, fixed):
                result[i] = t
            block.clear()

    for tok in _TAG.split(html):
        if _is_tag(tok):
            if _BLOCK_TAG.match(tok):
                flush()
            result.append(tok)
        else:
            block.append(len(result))
            result.append(tok)
    flush()
    out = "".join(result)
    if out != before:
        rep.fixes.append("Guillemets normalisés en « » avec espaces insécables.")
    return out


# --- 3b. Séparateurs et légende d'illustration : ce n'est pas au LLM d'en décider -----------------------------
_COVER_CAPTION = re.compile(r"<p\b[^>]*>\s*(?:<[^>]+>\s*)*Illustration de couverture\s*:.*?</p>\s*", re.S | re.I)


def fix_separators(html: str, rep: Report) -> str:
    """Seuls séparateurs voulus par la spec : après l'introduction du traducteur (ajoutée par build_intro) et
    en toute fin d'article s'il y a des notes (fix_notes). Ceux du LLM sont retirés. Une légende
    « Illustration de couverture » n'a de sens que pour une illustration choisie par un humain : retirée."""
    out, n_cap = _COVER_CAPTION.subn("", html)
    if n_cap:
        rep.fixes.append("Légende « Illustration de couverture » inventée par le LLM supprimée (aucune illustration n'est choisie par le programme).")
    out, n_dash = re.subn(r"(?m)^[ \t]*-{3,}[ \t]*$\n?", "", out)  # « --- » markdown laissés par le LLM
    out, n_hr = re.subn(r"\s*<hr\s*/?>\s*", "\n", out)
    n_hr += n_dash
    if n_hr:
        rep.fixes.append(f"{n_hr} séparateur(s) ajouté(s) par le LLM retiré(s).")
    return out.strip()


# --- 4. Notes de bas de page [[ ... ]] ------------------------------------------------------------------
_NOTE = re.compile(r"\[\[(.*?)\]\]", re.S)
_END_PUNCT = re.compile(r"[.!?…»]\s*$")


def fix_notes(html: str, rep: Report) -> str:
    html, n_runs = re.subn(r"\[{4,}", "[[[", html)  # « [[[[ » : le LLM a ouvert la note avec trop de crochets
    if n_runs:
        rep.fixes.append(f"{n_runs} ouverture(s) de note « [[[[ » ramenée(s) à « [[[ ».")
    if html.count("[[") != html.count("]]"):
        rep.warnings.append("Crochets de notes [[ ]] non appariés : vérifier les notes de bas de page.")
    if "[[" not in html:
        return html
    def drop_empty(m: re.Match) -> str:  # note vide : le LLM a inséré une note sans contenu (« [[Traduction libre.]] »)
        content = re.sub(r"\[Traduction libre\]|\(NDT\.\)|<[^>]+>|[\s.,;:!?…]", "", m.group(1), flags=re.I)
        content = re.sub(r"traductionlibre|ndt", "", content, flags=re.I)
        if content:
            return m.group(0)
        rep.fixes.append(f"Note vide « {m.group(0)} » supprimée (aucun contenu : note inventée).")
        return ""

    html = _NOTE.sub(drop_empty, html)
    if "[[" not in html:
        return html
    swaps = 0

    def swap(m: re.Match) -> str:  # « insérer cette note avant toute ponctuation »
        nonlocal swaps
        punct, note = m.group(1), m.group(2)
        swaps += 1
        return note + ("" if m.string[m.end():].startswith(punct) else punct)

    html = re.sub(r"([.,;:!?…]+)(\[\[.*?\]\])", swap, html, flags=re.S)
    if swaps:
        rep.fixes.append(f"{swaps} note(s) déplacée(s) avant la ponctuation.")

    ended = 0
    tl_removed: list[int] = []

    def end_punct(m: re.Match) -> str:  # « terminer la note par une ponctuation »
        nonlocal ended
        inner = m.group(1)
        if not _END_PUNCT.search(_TAG.sub("", inner)):
            ended += 1
            inner = inner.rstrip() + "."
        if "(NDT.)" in inner:
            rep.warnings.append("Note marquée (NDT.) : vérifier qu'il s'agit bien d'une note du traducteur et non d'une note de l'auteur.")
        has_tl = inner.lstrip().startswith("[Traduction libre]")
        if has_tl and "«" not in inner:  # balise réservée aux citations traduites : sans guillemets, pas de citation
            inner = re.sub(r"^\s*\[Traduction libre\]\s*", "", inner)
            tl_removed.append(1)
            has_tl = False
        if "«" in inner and not has_tl:
            rep.warnings.append("Note avec citation entre « » ne commençant pas par [Traduction libre] : à vérifier si la citation est traduite.")
        return f"[[{inner}]]"

    html = _NOTE.sub(end_punct, html)
    if tl_removed:
        rep.fixes.append(f"[Traduction libre] retiré de {len(tl_removed)} note(s) sans citation entre « » (balise réservée aux citations traduites).")
    if ended:
        rep.fixes.append(f"{ended} note(s) terminée(s) par un point.")
    if not re.search(r"<hr\s*/?>\s*$", html.rstrip()):  # « séparateur en toute fin d'article »
        html = html.rstrip() + "\n<hr>"
        rep.fixes.append("Séparateur ajouté en fin d'article (l'article a des notes).")
    return html


# --- 5. Références bibliques « Livre Chapitre,Verset » ------------------------------------------------
_ABBREV_CONTEXT = re.compile(r"(\[\[.*?\]\]|<li\b.*?</li>)", re.S)


def fix_bible_refs(html: str, rep: Report, abbrevs: dict[str, str]) -> str:
    """Abréviation si la référence est dans une liste (<li>) ou une note [[ ]], nom complet sinon."""
    total = 0
    missing = False
    parts = _ABBREV_CONTEXT.split(html)
    for i, part in enumerate(parts):
        inside = i % 2 == 1

        def sub(t: str) -> str:
            nonlocal total, missing
            new, n, miss = bible.normalize_refs(t, inside, abbrevs)
            total += n
            missing = missing or miss
            return new

        parts[i] = _map_text(part, sub)
    if total:
        rep.fixes.append(f"{total} référence(s) biblique(s) mises au format « Livre Chapitre,Verset ».")
    if missing:
        rep.warnings.append("Références bibliques en liste/note laissées en toutes lettres : abréviations non fournies (bible_abbreviations.toml).")
    out = "".join(parts)
    for m in re.finditer(r"\b([A-ZÉ][\wéèêëôûîïç]+)[  ](\d{1,3}):(\d{1,3})\b", _text_only(out)):
        rep.warnings.append(f"Référence biblique possible non reconnue : « {m.group(0)} » (livre absent de la liste Segond 21 ?).")
    return out


# --- 5b. URL nues -> liens explicites (sinon WordPress.com les relie lui-même et avale « ]] » dans le lien) --
_URL = re.compile(r"https?://[^\s<>\]\[]+")


def fix_urls(html: str, rep: Report) -> str:
    """WordPress transforme toute URL nue en lien, en y englobant la ponctuation qui suit (dont « ]] » qui ferme une
    note). On crée donc le lien nous-mêmes, sans la ponctuation finale, en laissant intacts les liens existants."""
    count = 0
    in_anchor = False
    out = []
    for tok in _TAG.split(html):
        if _is_tag(tok):
            if re.match(r"<a\b", tok, re.I):
                in_anchor = True
            elif re.match(r"</a\s*>", tok, re.I):
                in_anchor = False
            out.append(tok)
            continue
        if in_anchor:
            out.append(tok)
            continue

        def link(m: re.Match) -> str:
            nonlocal count
            url = m.group(0)
            trail = ""
            while url and url[-1] in ".,;:!?)»”\"'":
                trail = url[-1] + trail
                url = url[:-1]
            count += 1
            return f'<a href="{url}">{url}</a>{trail}'

        out.append(_URL.sub(link, tok))
    if count:
        rep.fixes.append(f"{count} URL nue(s) transformée(s) en lien explicite (évite que WordPress avale la ponctuation ou « ]] »).")
    return "".join(out)


# --- 6. Introduction du traducteur (italique + séparateur) ---------------------------------------------
def build_intro(url: str, original_title: str) -> str:
    """« S'il y a une introduction du traducteur : la mettre en italique et la séparer du corps par un séparateur »."""
    return (f'<p><em>Cet article est la traduction de <a href="{htmllib.escape(url)}">{htmllib.escape(original_title)}</a>.</em></p>\n'
            "<hr>\n")


# --- 6b. Identifiant (slug) de l'article : court, seulement les noms et les mots importants -------------
# Mots supprimés (écrits sans accents) : déterminants, prépositions, pronoms, conjonctions, interrogatifs, formes des
# verbes être/avoir/faire/pouvoir et adverbes courants.
_SLUG_STOPWORDS = set("""
le la les l un une des du de d au aux et ou mais donc or ni car que qu qui quoi dont ou ce cet cette ces se sa son ses
mon ma mes ton ta tes notre nos votre vos leur leurs je j tu il elle on nous vous ils elles me te lui eux y en
dans sur sous par pour avec sans chez vers entre contre selon comme si ne n pas
est sont etait etaient etre ete sera seront serait soit sois suis es sommes etes fut fusse
a ont avait avaient avoir aura auront aurait ai as avons avez eu
fait font faire fera ferait peut peuvent pouvoir pourrait doit doivent devoir
quel quels quelle quelles quoi comment pourquoi quand combien lequel laquelle
tout tous toute toutes autre autres meme memes tel telle tels telles chaque plusieurs
plus moins tres trop assez aussi encore toujours jamais souvent deja vraiment reellement seulement
ici la voici voila alors ainsi donc puis enfin apres avant pendant depuis
""".split())
_SLUG_MAX_WORDS = 6
_SLUG_MAX_CHARS = 60


def _fold(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).replace("œ", "oe").replace("æ", "ae")


def clean_slug(text: str) -> str:
    """Minuscules sans accents, mots séparés par des tirets, déterminants & co retirés, versets collés (29,11 -> 2911),
    au plus 6 mots et 60 caractères."""
    t = _fold(htmllib.unescape(text)).lower()
    t = re.sub(r"(?<=\d)\s?[,:.]\s?(?=\d)", "", t)  # « 29,11 » / « 29:11 » -> « 2911 »
    words = [w for w in re.split(r"[^a-z0-9]+", t) if w and w not in _SLUG_STOPWORDS]
    kept: list[str] = []
    for w in words[:_SLUG_MAX_WORDS]:
        if len("-".join(kept + [w])) > _SLUG_MAX_CHARS:
            break
        kept.append(w)
    return "-".join(kept)


def make_slug(candidate: str | None, title: str) -> tuple[str, bool]:
    """Identifiant final : celui proposé par le LLM (nettoyé), sinon construit à partir du titre.
    Retourne (slug, venait_du_titre)."""
    slug = clean_slug(candidate or "")
    if slug:
        return slug, False
    return clean_slug(title), True


# --- 7. Contrôles sans correction automatique -----------------------------------------------------------
def check(html: str, rep: Report) -> None:
    text = _text_only(html)
    if re.search(r"[IVXLCDM0-9]+ème\b", text):
        rep.warnings.append("« ème » encore présent dans le texte.")
    if '"' in text:
        rep.warnings.append('Guillemets droits (") restants dans le texte.')
    for m in re.finditer(r"<p>\s*«[^<]*»\s*</p>", html):  # un seul bloc de citation, plus d'une phrase
        if m.group(0).count("«") == 1 and len(re.findall(r"[.!?…]\s+\S", m.group(0))) >= 1:
            rep.warnings.append("Paragraphe entièrement entre « » de plus d'une phrase : à mettre en citation (blockquote) ?")
            break
    if re.search(r"</?h[12]\b", html, re.I):
        rep.warnings.append("Titre H1/H2 résiduel.")


def apply_all(html: str, abbrevs: dict[str, str] | None = None) -> tuple[str, Report]:
    rep = Report()
    html = fix_tags(html, rep)
    html = fix_headings(html, rep)
    html = fix_ordinals(html, rep)
    html = fix_quotes(html, rep)
    html = fix_separators(html, rep)
    html = fix_bible_refs(html, rep, abbrevs or {})
    html = fix_urls(html, rep)
    html = fix_notes(html, rep)
    check(html, rep)
    return html, rep
