"""Chaîne commune à agent.py (publication) et dry_run.py (aperçu) : prompt avec les specs -> LLM -> règles."""
import html as htmllib
import re
from dataclasses import dataclass, field
from pathlib import Path

import bible
import rules
import templating
from extract import Article
from llm_browser import Browser, LLMUnavailable, parse_answer
from specs import load_specs

# Ce que le code ne peut pas faire à la place d'un humain : à cocher à chaque article (voir la spec).
MANUAL_CHECKLIST = [
    "Cocher « Enable Monarch Settings Override » en bas de la page de l'éditeur WP (partage des articles).",
    "Choisir une illustration libre de droits et compléter sa légende en fin d'article : remplacer « Artiste À COMPLÉTER », "
    "« Titre de l'œuvre » (déjà en italique), « technique » et « date » (même forme que les modèles publiés).",
    "Relire l'introduction du traducteur (résumé écrit par le LLM) et y ajouter, si besoin, le contexte éditorial.",
    "Vérifier la catégorie et les étiquettes proposées.",
    "Vérifier que les ouvrages cités n'ont pas déjà été traduits en français (et le signaler dans les références).",
    "Relire : église/Église, Évangile/évangile, mots étrangers en italique, références bibliographiques (Lausanne).",
]


@dataclass
class Result:
    title: str
    tags: list[str]
    category: str | None
    html: str  # corps final, introduction du traducteur comprise
    engine: str
    slug: str = ""  # identifiant (partie finale de l'URL), court : noms et mots importants
    fixes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    to_check: list[str] = field(default_factory=list)


MAX_ATTEMPTS = 2  # essais par moteur quand la réponse est refusée (notes incohérentes, format, anglais non traduit)


def _grounded(item: str, source_text: str) -> bool:
    """Vrai si au moins un mot significatif (5+ lettres) de l'élément figure dans l'article source."""
    low = source_text.lower()
    words = [w for w in re.findall(r"[^\W\d_]{5,}", item.lower())]
    return any(w in low for w in words)


def _keep_rejected(art: Article, html: str) -> None:
    out = Path("output/rejected")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{slug(art.url)}.html").write_text(html, encoding="utf-8")


def make_prompt(art: Article, cfg: dict, categories: list[str]) -> str:
    specs = load_specs(cfg["specs"]["dir"], cfg["specs"].get("exclude_after"))
    cats = ", ".join(categories) if categories else "(aucune catégorie disponible : écris « CATEGORIE: aucune »)"
    return cfg["llm"]["prompt"].format(title=art.title, text=art.text, specs=specs, categories=cats,
                                       headings_info=headings_info(art))


def headings_info(art: Article) -> str:
    """Dit au LLM combien de titres/intertitres la source contient (et lesquels) : il n'en invente pas."""
    heads = rules.source_headings(art.text, art.title)
    if not heads:
        return ("La source ne contient AUCUN titre ni intertitre : n'écris AUCUN <h3> ni <h4>, ne donne pas de titre aux "
                "parties, ne répète pas le titre de l'article. Le corps n'est fait que de paragraphes (listes et citations "
                "si la source en a).")
    listing = " | ".join(f"{i}. {h}" for i, h in enumerate(heads, start=1))
    return (f"La source contient exactement {len(heads)} titre(s)/intertitre(s) : {listing}. Traduis-les, EN <h3>/<h4>, et "
            "n'en ajoute AUCUN autre.")


def translate_article(art: Article, cfg: dict, browser: Browser, categories: list[str] | None = None) -> Result:
    categories = categories or []
    tpl = templating.load_templates(cfg.get("templates", {}).get("dir", "articles_templates"))  # échoue AVANT d'appeler le LLM
    prompt = make_prompt(art, cfg, categories)
    abbrevs = bible.load_abbreviations()
    expected = len(set(re.findall(r"\[NOTE (\d+)\]", art.text)))
    errors = []
    accepted = None
    for engine in cfg["llm"]["engines"]:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                ans = parse_answer(browser.translate(engine, prompt))
                body, rep = rules.apply_all(ans.html, abbrevs)
                opens, closes = body.count("[["), body.count("]]")
                # Garde-fou BLOQUANT : une traduction avec des notes en trop (inventées), en moins (perdues) ou mal
                # fermées n'est jamais publiée. Le dernier essai refusé est conservé dans output/rejected/.
                if opens != closes or opens != expected or "[NOTE" in body or "NOTES DE BAS DE PAGE" in body:
                    _keep_rejected(art, ans.html)
                    raise ValueError(f"{expected} appel(s) de note dans la source mais {opens} « [[ » et {closes} « ]] » dans la traduction")
                accepted = (ans, body, rep)
                break
            except ValueError as e:
                errors.append(f"{engine} (essai {attempt}): {e}")
            except LLMUnavailable as e:
                errors.append(f"{engine}: {e}")
                break  # moteur indisponible : inutile de réessayer, on passe au suivant
        if accepted:
            break
    if not accepted:
        raise RuntimeError("Aucune traduction acceptable (rien n'est publié) : " + " | ".join(errors))
    ans, body, rep = accepted
    body = rules.drop_title_heading(body, ans.title, rep)
    src_heads = rules.source_headings(art.text, art.title)
    if not src_heads:  # garantie : une source sans titre ne donne jamais de titre, quoi que le LLM ait écrit
        body = rules.remove_all_headings(body, rep)

    before = len(ans.to_check)
    ans.to_check[:] = [i for i in ans.to_check if _grounded(i, art.text)]
    if len(ans.to_check) < before:
        rep.fixes.append(f"{before - len(ans.to_check)} élément(s) « à vérifier » écarté(s) : absents de l'article source "
                         "(le LLM avait repris des exemples des documents de règles).")
    src_headings = len(src_heads)
    out_headings = len(re.findall(r"<h[34]\b", body))
    if out_headings > src_headings:
        rep.warnings.append(f"{out_headings} titre(s) dans la traduction pour {src_headings} dans la source : "
                            "un intertitre a peut-être été inventé (ou le titre de l'article répété dans le corps).")
    slug, from_title = rules.make_slug(ans.slug, ans.title)
    if from_title:
        if rules.clean_slug(ans.slug or ""):
            rep.fixes.append(f"Identifiant (slug) proposé « {ans.slug} » écarté : un mot n'est pas dans le titre. "
                             f"Reconstruit à partir du titre : « {slug} ».")
        else:
            rep.fixes.append("Identifiant (slug) construit à partir du titre : le LLM n'en avait pas proposé d'exploitable.")
    elif ans.slug and slug != ans.slug:
        rep.fixes.append(f"Identifiant (slug) nettoyé : « {ans.slug} » -> « {slug} ».")
    category = ans.category
    if category and categories and category not in categories:
        rep.warnings.append(f"Catégorie proposée « {category} » absente du site : ignorée.")
        category = None
    # Mise en forme d'après les modèles publiés : introduction, séparateur, corps, séparateur, légende (+ séparateur final
    # s'il y a des notes). Le séparateur final ajouté par rules.fix_notes est remplacé par celui des modèles.
    has_notes = "[[" in body
    body_only = re.sub(r"\s*<hr\s*/?>\s*$", "", body)
    if not ans.summary:
        rep.warnings.append("Le LLM n'a pas fourni de résumé : l'introduction du traducteur n'en contient pas.")
    if not art.author:
        rep.warnings.append("Auteur d'origine inconnu : l'introduction dit « l'auteur » (à compléter avec son nom).")
    if not art.illustration:
        rep.warnings.append("Légende d'illustration à compléter : le repère « À COMPLÉTER » est dans le brouillon.")
    intro = templating.intro_inner(art.title, art.url, art.author, ans.summary or "")
    html = templating.assemble(intro, body_only, art.illustration, has_notes, tpl)
    return Result(
        title=ans.title, tags=ans.tags, category=category,
        html=html, engine=engine, slug=slug,
        fixes=rep.fixes, warnings=rep.warnings, to_check=ans.to_check,
    )


def write_review(path: Path, art: Article, res: Result, draft_url: str = "") -> None:
    """Fiche de relecture : ce qui a été corrigé, ce qui reste à vérifier, et les actions manuelles."""
    def bullets(items):
        return "\n".join(f"- {i}" for i in items) or "- (rien)"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Relecture : {res.title}\n\nSource : {art.url or '(fichier .md local, adresse d origine inconnue)'}\n"
        f"Brouillon : {draft_url or '(non publié)'}\n"
        f"Moteur : {res.engine} | Catégorie : {res.category or '(aucune)'} | Étiquettes : {', '.join(res.tags)}\n"
        f"Identifiant (slug) : {res.slug or '(aucun)'}\n\n"
        f"## Corrections automatiques appliquées\n{bullets(res.fixes)}\n\n"
        f"## Avertissements (à vérifier)\n{bullets(res.warnings)}\n\n"
        f"## Signalé par le traducteur LLM (ouvrages / références à vérifier)\n{bullets(res.to_check)}\n\n"
        f"## Actions manuelles dans WordPress\n{bullets('[ ] ' + c for c in MANUAL_CHECKLIST)}\n",
        encoding="utf-8",
    )


RESULTS_DIR = Path("output/results")


def result_id(key: str, mode: str) -> str:
    """Identifiant stable d'un résultat : mode (« brouillon » ou « apercu ») + nom de l'article."""
    name = key[3:] if key.startswith("md:") else key
    return f"{mode}-{slug(name)}"


def save_result(key: str, art: Article, res: Result, draft_url: str, mode: str) -> Path:
    """Enregistre le résultat complet (HTML, avertissements…) pour l'interface : output/results/<id>.json.
    Un nouveau passage sur le même article remplace l'ancien résultat du même mode."""
    import datetime
    import json

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rid = result_id(key, mode)
    data = {
        "id": rid, "key": key, "mode": mode, "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "source_url": art.url, "source_title": art.title, "author": art.author,
        "title": res.title, "slug": res.slug, "tags": res.tags, "category": res.category, "engine": res.engine,
        "draft_url": draft_url, "html": res.html, "warnings": res.warnings, "fixes": res.fixes,
        "to_check": res.to_check, "manual": MANUAL_CHECKLIST,
    }
    path = RESULTS_DIR / f"{rid}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def slug(url: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", url.rstrip("/").split("/")[-1].lower()).strip("-")[:50] or "article"


def preview_html(art: Article, res: Result) -> str:
    return (f'<!doctype html><meta charset="utf-8"><title>{htmllib.escape(res.title)}</title>\n'
            '<body style="max-width:46rem;margin:2rem auto;font:18px/1.6 Georgia,serif;padding:0 1rem">\n'
            f'<p style="color:#666;font:14px sans-serif">Catégorie : {htmllib.escape(res.category or "-")} | '
            f'Tags : {htmllib.escape(", ".join(res.tags))} | Identifiant : {htmllib.escape(res.slug)} | {res.engine}</p>\n'
            f"<h1>{htmllib.escape(res.title)}</h1>\n{res.html}")
