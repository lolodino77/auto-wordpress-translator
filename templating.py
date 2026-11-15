"""Mise en forme finale d'un article d'après les modèles d'articles déjà publiés (dossier articles_templates/).

Structure commune des modèles, que cette étape reproduit :
  1. introduction du traducteur (paragraphe en italique : « Cet article est la traduction de l'article … »)
  2. séparateur « barre »
  3. corps de l'article (un bloc par paragraphe, titre, liste ou citation)
  4. séparateur « barre »
  5. légende de l'illustration (paragraphe en petite taille)
  (+ un séparateur final si l'article a des notes de bas de page : spec « Règles de rédaction des articles »)

Le balisage exact (blocs WordPress, classes, attributs des liens) est LU dans les modèles, pas écrit en dur : si les
modèles changent, les nouveaux articles suivent. Un modèle qui n'a pas cette structure est refusé avec un message clair.
"""
import html as htmllib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import rules

NBSP = " "
_BLOCK = re.compile(r"<!-- wp:([a-z-]+)(?: (\{.*?\}))? -->.*?<!-- /wp:\1 -->", re.S)
_SEPARATOR = re.compile(r"<!-- wp:separator -->\s*<hr[^>]*/?>\s*<!-- /wp:separator -->")
_CAPTION = re.compile(r'(<!-- wp:paragraph \{"fontSize":"small"\} -->\s*<p class="has-small-font-size">)(.*?)'
                      r"(</p>\s*<!-- /wp:paragraph -->)", re.S)
_LINK_ATTRS = re.compile(r'<a href="[^"]+" target="([^"]+)" rel="([^"]+)">')
_TOP_LEVEL = re.compile(r"<(p|h[1-6]|ul|ol|blockquote)\b[^>]*>(.*?)</\1>", re.S | re.I)
_PLAIN_LINK = re.compile(r'<a href="(https?://[^"]*)">')

PLACEHOLDER_CAPTION = ("Illustration de couverture : <strong>À COMPLÉTER</strong> "
                       "(artiste, <em>titre de l'œuvre</em>, technique, date, lieu de conservation).")


@dataclass(frozen=True)
class Templates:
    separator: str  # bloc séparateur exact des modèles
    caption_open: str  # début du bloc de légende (petite taille)
    caption_close: str
    link_target: str  # attributs des liens dans les modèles (le plus fréquent)
    link_rel: str
    sources: tuple[str, ...]  # noms des modèles lus


def block_sequence(text: str) -> list[tuple[str, str]]:
    """Blocs de premier niveau d'un texte : [(nom, attributs)]. Un éventuel titre en texte brut avant le 1er bloc est ignoré."""
    start = text.find("<!--")
    return [(m.group(1), m.group(2) or "") for m in _BLOCK.finditer(text[max(start, 0):])]


def check_structure(text: str, label: str, allow_final_separator: bool = False) -> None:
    """Vérifie : introduction, séparateur, corps, séparateur, légende (+ séparateur final si des notes existent)."""
    seq = block_sequence(text)
    names = [n for n, _ in seq]
    if allow_final_separator and len(names) >= 2 and names[-1] == "separator":
        seq, names = seq[:-1], names[:-1]
    ok = (len(names) >= 5 and names[0] == "paragraph" and names[1] == "separator"
          and names[-2] == "separator" and names[-1] == "paragraph" and "fontSize" in seq[-1][1])
    if not ok:
        raise ValueError(f"{label} : structure inattendue {names[:3]}…{names[-3:]} (attendu : introduction, séparateur, corps, "
                         "séparateur, légende en petite taille)")


def load_templates(directory: str = "articles_templates") -> Templates:
    files = sorted(Path(directory).glob("*.html"))
    if not files:
        raise FileNotFoundError(f"Aucun modèle .html dans {directory}/ (un article publié, copié depuis l'éditeur de code)")
    texts = {f.name: f.read_text(encoding="utf-8-sig") for f in files}
    for name, text in texts.items():
        check_structure(text, name)
    first = next(iter(texts.values()))
    sep = _SEPARATOR.search(first)
    cap = _CAPTION.search(first)
    if not sep or not cap:
        raise ValueError("Modèle sans séparateur ou sans légende reconnaissable")
    links = Counter()
    for text in texts.values():
        links.update(_LINK_ATTRS.findall(text))
    target, rel = links.most_common(1)[0][0] if links else ("_blank", "noopener")
    return Templates(sep.group(0).strip(), cap.group(1).strip(), cap.group(3).strip(), target, rel, tuple(texts))


def externalize_links(html: str, tpl: Templates) -> str:
    """Les liens externes s'ouvrent dans un nouvel onglet, avec les attributs des modèles."""
    return _PLAIN_LINK.sub(lambda m: f'<a href="{m.group(1)}" target="{tpl.link_target}" rel="{tpl.link_rel}">', html)


def _block(tag: str, inner: str) -> str:
    inner = inner.strip()
    if tag == "p":
        return f"<!-- wp:paragraph -->\n<p>{inner}</p>\n<!-- /wp:paragraph -->"
    if re.fullmatch(r"h[1-6]", tag):
        level = int(tag[1])
        attrs = "" if level == 2 else f' {{"level":{level}}}'
        return f'<!-- wp:heading{attrs} -->\n<{tag} class="wp-block-heading">{inner}</{tag}>\n<!-- /wp:heading -->'
    if tag in ("ul", "ol"):
        items = re.findall(r"<li\b[^>]*>(.*?)</li>", inner, re.S)
        li = "\n\n".join(f"<!-- wp:list-item -->\n<li>{i.strip()}</li>\n<!-- /wp:list-item -->" for i in items)
        attrs = ' {"ordered":true}' if tag == "ol" else ""
        return f'<!-- wp:list{attrs} -->\n<{tag} class="wp-block-list">{li}</{tag}>\n<!-- /wp:list -->'
    if tag == "blockquote":
        paras = re.findall(r"<p\b[^>]*>(.*?)</p>", inner, re.S) or [inner]
        ps = "\n\n".join(f"<!-- wp:paragraph -->\n<p>{p.strip()}</p>\n<!-- /wp:paragraph -->" for p in paras)
        return f'<!-- wp:quote -->\n<blockquote class="wp-block-quote">{ps}</blockquote>\n<!-- /wp:quote -->'
    raise ValueError(tag)


def to_blocks(body_html: str) -> list[str]:
    """Convertit le HTML simple du corps en blocs WordPress. Un texte hors balise reconnue devient un paragraphe."""
    blocks, pos = [], 0
    for m in _TOP_LEVEL.finditer(body_html):
        stray = body_html[pos:m.start()].strip()
        if stray:
            blocks.append(_block("p", stray))
        blocks.append(_block(m.group(1).lower(), m.group(2)))
        pos = m.end()
    tail = body_html[pos:].strip()
    if tail:
        blocks.append(_block("p", tail))
    return blocks


def _de(name: str) -> str:
    """« de Edward » -> « d'Edward » (élision devant une voyelle)."""
    return ("d'" if name[:1] in "AEIOUYÀÂÉÈÊËÎÏÔÙÛÜaeiouyàâéèêëîïôùûü" else "de ") + name


def intro_inner(title: str, url: str, author: str, summary: str) -> str:
    """Introduction : « Cet article est la traduction de l'article <lien> de <auteur>, dans lequel <auteur> <résumé>. »
    Le résumé est écrit par le LLM à partir du texte ; l'auteur vient des métadonnées, jamais deviné (aucun pronom)."""
    t = htmllib.escape(title)
    text = "Cet article est la traduction de l'article " + (f'<a href="{htmllib.escape(url)}">{t}</a>' if url
                                                            else f"«{NBSP}{t}{NBSP}»")
    author = author.strip()
    if author:
        text += " " + _de(htmllib.escape(author))
    summary = summary.strip().rstrip(".") if summary else ""
    if summary[:1].isupper() and summary[1:2].islower():  # la phrase continue après « dans lequel <auteur> » : pas de majuscule
        summary = summary[0].lower() + summary[1:]
    if summary:
        text += f", dans lequel {htmllib.escape(author) if author else 'l’auteur'} {htmllib.escape(summary, quote=False)}"
    return rules.apply_all(f"<em>{text}.</em>")[0]


def caption_inner(illustration: str) -> str:
    """Légende : texte fourni (CSV ou en-tête du .md), sinon un repère « À COMPLÉTER » bien visible."""
    text = (illustration or "").strip()
    if not text:
        return PLACEHOLDER_CAPTION
    text = htmllib.escape(text, quote=False)
    text = re.sub(r"\*([^*]+)\*|(?<!\w)_([^_]+)_(?!\w)", lambda m: f"<em>{m.group(1) or m.group(2)}</em>", text)
    if not re.match(r"(?i)illustration", text):
        text = "Illustration de couverture : " + text
    return rules.apply_all(text)[0]


def assemble(intro: str, body_html: str, illustration: str, has_notes: bool, tpl: Templates) -> str:
    """Article final : introduction, séparateur, corps, séparateur, légende (+ séparateur final s'il y a des notes)."""
    blocks = [
        f"<!-- wp:paragraph -->\n<p>{externalize_links(intro, tpl)}</p>\n<!-- /wp:paragraph -->",
        tpl.separator,
        *to_blocks(externalize_links(body_html, tpl)),
        tpl.separator,
        f"{tpl.caption_open}{caption_inner(illustration)}{tpl.caption_close}",
    ]
    if has_notes:
        blocks.append(tpl.separator)
    return "\n\n".join(blocks).replace(NBSP, "&nbsp;")
