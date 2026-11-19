"""Agent de traduction EN->FR : extraction, traduction via navigateur, brouillon WordPress.

Usage :
  python agent.py --login          # une fois : se connecter à Gemini/ChatGPT dans le profil
  python agent.py --auth           # une fois : identifiants WordPress (OAuth WordPress.com ou mot de passe d'application)
  python agent.py                  # traite les URLs de input/articles.csv (celles déjà faites sont sautées)
  python agent.py --md             # traite les fichiers .md de input/articles_md/ (même pipeline)
  python agent.py --md AUTRE/DOSSIER --only 2 --force
"""
import argparse
import logging
import re
import sqlite3
import tomllib
from pathlib import Path

import wp
from inputs import csv_jobs, label, md_jobs
from llm_browser import Browser
from pipeline import save_result, slug, translate_article, write_review

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("agent.log", encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("agent")


def backend(cfg: dict):
    """Module d'accès à WordPress selon config.toml : « wpcom » (OAuth, wp.py) ou « selfhosted » (wp_selfhosted.py)."""
    mode = cfg["wordpress"].get("mode", "wpcom")
    if mode == "selfhosted":
        import wp_selfhosted
        return wp_selfhosted
    if mode == "wpcom":
        return wp
    raise ValueError(f"mode inconnu dans config.toml : {mode!r} (attendu : 'wpcom' ou 'selfhosted')")


def open_db(site: str, directory: str | Path = ".") -> sqlite3.Connection:
    """Une base d'état PAR SITE : un article déjà publié sur un site n'est pas considéré comme fait pour un autre."""
    host = re.sub(r"[^a-z0-9]+", "-", site.lower().removeprefix("https://").removeprefix("http://")).strip("-")
    db = sqlite3.connect(Path(directory) / f"state-{host}.db", timeout=15)
    db.execute("CREATE TABLE IF NOT EXISTS jobs (url TEXT PRIMARY KEY, status TEXT, info TEXT)")
    return db


def set_status(db, url, status, info=""):
    db.execute("INSERT OR REPLACE INTO jobs VALUES (?,?,?)", (url, status, info))
    db.commit()


_POST_ID = re.compile(r"[?&](?:post|p)=(\d+)")
GONE = {"trash", "missing"}  # brouillon mis à la corbeille ou supprimé dans WordPress


def reconcile(db, cfg: dict, keys=None) -> dict[str, str]:
    """Met la base locale d'accord avec le site : un brouillon mis à la corbeille ou supprimé dans WordPress rend son
    article de nouveau « à traduire » (état « removed ») ; un brouillon sorti de la corbeille redevient « fait ».
    Lecture seule côté site. Retourne {clé: état WordPress}. Si le site ne répond pas, la base locale reste telle quelle."""
    mod = backend(cfg)
    if not hasattr(mod, "post_states"):  # WordPress.com : pas de vérification
        return {}
    rows = db.execute("SELECT url, status, info FROM jobs WHERE status IN ('published', 'removed')").fetchall()
    ids = {k: (status, int(m.group(1))) for k, status, info in rows
           if (keys is None or k in keys) and (m := _POST_ID.search(info or ""))}
    if not ids:
        return {}
    try:
        states = mod.post_states(cfg["wordpress"]["site"], sorted({pid for _, pid in ids.values()}))
    except Exception as e:
        log.warning("État des brouillons illisible sur le site (%s) : on se fie à la base locale.", e)
        return {}
    db_rows = {k: info for k, _, info in rows}
    out = {}
    for key, (status, pid) in ids.items():
        wp_status = states.get(pid, "unknown")
        out[key] = wp_status
        if status == "published" and wp_status in GONE:
            set_status(db, key, "removed", db_rows[key])  # on garde l'adresse de l'ancien brouillon
            log.info("Brouillon n° %s %s dans WordPress : %s redevient à traduire.", pid,
                     "mis à la corbeille" if wp_status == "trash" else "supprimé", key)
        elif status == "removed" and wp_status not in GONE | {"unknown", "inaccessible"}:
            set_status(db, key, "published", db_rows[key])
            log.info("Brouillon n° %s de nouveau présent dans WordPress (%s) : %s est fait.", pid, wp_status, key)
    return out


def process(key: str, csv_tags: list[str], load, cfg: dict, browser: Browser, categories: list[str],
            on_step=None, preview: bool = False) -> str:
    """Pipeline d'un travail (URL du CSV ou fichier .md) : chargement, traduction, règles, brouillon, fiche de relecture.
    on_step(étape) est appelé à chaque étape (pour l'interface). preview=True : tout sauf la création du brouillon."""
    step = on_step or (lambda name: None)
    url = key
    step("load")
    art = load()
    if len(art.text.split()) > cfg["llm"]["max_words"]:
        raise RuntimeError("Article trop long, à découper à la main")
    step("translate")
    res = translate_article(art, cfg, browser, categories)
    res.tags = list(dict.fromkeys(csv_tags + res.tags))  # tags de la source ignorés : en anglais
    draft = ""
    if not preview:
        step("publish")
        draft = backend(cfg).create_draft(cfg["wordpress"]["site"], res.title, res.html, res.tags,
                                          [res.category] if res.category else None, res.slug)
        res.warnings.extend(getattr(backend(cfg), "last_warnings", []))  # ex. étiquettes non posées (site restreint)
    prefix = "essai-" if preview else ""  # un essai n'écrase pas la fiche de relecture d'un vrai brouillon
    write_review(Path("output/review") / f"{prefix}{slug(label(key))}.md", art, res, draft)
    save_result(key, art, res, draft, "apercu" if preview else "brouillon")
    for w in res.warnings:
        log.warning("%s : %s", url, w)
    step("done")
    return draft


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--auth", action="store_true", help="autoriser WordPress.com (ID et secret saisis dans le terminal)")
    ap.add_argument("--csv", default="input/articles.csv", help="une URL par ligne (étiquettes en 2e colonne, séparées par ;)")
    ap.add_argument("--md", nargs="?", const="input/articles_md", default=None, metavar="DOSSIER",
                    help="au lieu du CSV, traite chaque fichier .md du dossier (défaut : input/articles_md)")
    ap.add_argument("--force", action="store_true", help="retraite aussi les articles déjà faits (crée de nouveaux brouillons)")
    ap.add_argument("--only", type=int, default=None,
                    help="ne traiter que l'élément N de la liste (1 = premier), même s'il est déjà fait")
    args = ap.parse_args()

    cfg = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))

    if args.auth:
        import getpass

        wp_cfg = cfg["wordpress"]
        if wp_cfg.get("mode", "wpcom") == "selfhosted":
            print(f"Site auto-hébergé : {wp_cfg['site']}. Le mot de passe d'application est lié à l'utilisateur indiqué.")
            who = backend(cfg).authorize(wp_cfg["site"], input("Nom d'utilisateur WordPress : ").strip(),
                                         getpass.getpass("Mot de passe d'application (masqué) : ").strip())
            print(f"Identifiants valides et enregistrés (wp_credentials.json). Compte : {who.get('slug')!r}, "
                  f"rôle(s) : {who.get('roles')}")
            return
        print(f"Droits demandés : {wp_cfg.get('scope') or '(défaut de WordPress.com : large)'} | site : {wp_cfg['site']}")
        wp.authorize(input("Client ID : ").strip(), getpass.getpass("Client secret (masqué) : ").strip(),
                     wp_cfg.get("scope") or None, wp_cfg["site"])
        return
    if args.login:
        with Browser(cfg["llm"]["profile_dir"]) as b:
            b.login_session()
        return

    db = open_db(cfg["wordpress"]["site"])
    if not args.force:
        reconcile(db, cfg)  # un brouillon mis à la corbeille dans WordPress ne compte plus comme « fait »
    done = set() if args.force else {r[0] for r in db.execute("SELECT url FROM jobs WHERE status='published'")}
    jobs = md_jobs(args.md) if args.md is not None else csv_jobs(args.csv)
    todo = [(k, t, load) for i, (k, t, load) in enumerate(jobs, start=1)
            if (args.only is None or i == args.only) and (k not in done or args.only)]
    log.info("%d article(s) à traiter (source : %s)", len(todo), f"dossier {args.md}" if args.md is not None else args.csv)
    if not todo:
        return
    try:
        categories = backend(cfg).list_categories(cfg["wordpress"]["site"])
    except Exception as e:  # sans catégories, le LLM n'en propose pas ; l'article reste créé
        categories = []
        log.warning("Catégories du site illisibles (%s) : aucune catégorie ne sera proposée", e)

    with Browser(cfg["llm"]["profile_dir"], cfg["llm"]["headless"], prefs=cfg["llm"], log=print) as browser:
        for key, csv_tags, load in todo:
            try:
                draft = process(key, csv_tags, load, cfg, browser, categories)
                set_status(db, key, "published", draft)  # « published » = traité : un BROUILLON a été créé, jamais publié
                log.info("OK %s -> %s", key, draft)
            except Exception as e:
                set_status(db, key, "error", str(e))
                log.error("ECHEC %s : %s", key, e)

    names = {"published": "brouillon créé", "error": "erreur", "removed": "ancien brouillon supprimé : à traduire"}
    for key, status, info in db.execute("SELECT * FROM jobs"):
        print(f"[{names.get(status, status)}] {key} {info}")


if __name__ == "__main__":
    main()
