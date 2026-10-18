"""Chaîne commune à agent.py (publication) et dry_run.py (aperçu) : prompt avec les specs -> LLM -> règles."""
import html as htmllib
import re
from dataclasses import dataclass, field
from pathlib import Path

import bible
import rules
from extract import Article
from llm_browser import Browser, LLMUnavailable, parse_answer
from specs import load_specs

# Ce que le code ne peut pas faire à la place d'un humain : à cocher à chaque article (voir la spec).
MANUAL_CHECKLIST = [
    "Cocher « Enable Monarch Settings Override » en bas de la page de l'éditeur WP (partage des articles).",
    "Choisir une illustration libre de droits et ajouter sa légende en fin d'article (« Illustration de couverture : », "
    "police « petite », au-dessus du séparateur des notes s'il y en a ; pas de séparateur au-dessus de la légende).",
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
    return cfg["llm"]["prompt"].format(title=art.title, text=art.text, specs=specs, categories=cats)


def translate_article(art: Article, cfg: dict, browser: Browser, categories: list[str] | None = None) -> Result:
    categories = categories or []
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

    before = len(ans.to_check)
    ans.to_check[:] = [i for i in ans.to_check if _grounded(i, art.text)]
    if len(ans.to_check) < before:
        rep.fixes.append(f"{before - len(ans.to_check)} élément(s) « à vérifier » écarté(s) : absents de l'article source "
                         "(le LLM avait repris des exemples des documents de règles).")
    slug, from_title = rules.make_slug(ans.slug, ans.title)
    if from_title:
        rep.fixes.append("Identifiant (slug) construit à partir du titre : le LLM n'en avait pas proposé d'exploitable.")
    elif ans.slug and slug != ans.slug:
        rep.fixes.append(f"Identifiant (slug) nettoyé : « {ans.slug} » -> « {slug} ».")
    category = ans.category
    if category and categories and category not in categories:
        rep.warnings.append(f"Catégorie proposée « {category} » absente du site : ignorée.")
        category = None
    return Result(
        title=ans.title, tags=ans.tags, category=category,
        html=rules.build_intro(art.url, art.title) + body, engine=engine, slug=slug,
        fixes=rep.fixes, warnings=rep.warnings, to_check=ans.to_check,
    )


def write_review(path: Path, art: Article, res: Result, draft_url: str = "") -> None:
    """Fiche de relecture : ce qui a été corrigé, ce qui reste à vérifier, et les actions manuelles."""
    def bullets(items):
        return "\n".join(f"- {i}" for i in items) or "- (rien)"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Relecture : {res.title}\n\nSource : {art.url}\nBrouillon : {draft_url or '(non publié)'}\n"
        f"Moteur : {res.engine} | Catégorie : {res.category or '(aucune)'} | Étiquettes : {', '.join(res.tags)}\n"
        f"Identifiant (slug) : {res.slug or '(aucun)'}\n\n"
        f"## Corrections automatiques appliquées\n{bullets(res.fixes)}\n\n"
        f"## Avertissements (à vérifier)\n{bullets(res.warnings)}\n\n"
        f"## Signalé par le traducteur LLM (ouvrages / références à vérifier)\n{bullets(res.to_check)}\n\n"
        f"## Actions manuelles dans WordPress\n{bullets('[ ] ' + c for c in MANUAL_CHECKLIST)}\n",
        encoding="utf-8",
    )


def slug(url: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", url.rstrip("/").split("/")[-1].lower()).strip("-")[:50] or "article"


def preview_html(art: Article, res: Result) -> str:
    return (f'<!doctype html><meta charset="utf-8"><title>{htmllib.escape(res.title)}</title>\n'
            '<body style="max-width:46rem;margin:2rem auto;font:18px/1.6 Georgia,serif;padding:0 1rem">\n'
            f'<p style="color:#666;font:14px sans-serif">Catégorie : {htmllib.escape(res.category or "-")} | '
            f'Tags : {htmllib.escape(", ".join(res.tags))} | Identifiant : {htmllib.escape(res.slug)} | {res.engine}</p>\n'
            f"<h1>{htmllib.escape(res.title)}</h1>\n{res.html}")
