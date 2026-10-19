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
from pipeline import slug, translate_article, write_review

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


def open_db(site: str) -> sqlite3.Connection:
    """Une base d'état PAR SITE : un article déjà publié sur un site n'est pas considéré comme fait pour un autre."""
    host = re.sub(r"[^a-z0-9]+", "-", site.lower().removeprefix("https://").removeprefix("http://")).strip("-")
    db = sqlite3.connect(f"state-{host}.db")
    db.execute("CREATE TABLE IF NOT EXISTS jobs (url TEXT PRIMARY KEY, status TEXT, info TEXT)")
    return db


def set_status(db, url, status, info=""):
    db.execute("INSERT OR REPLACE INTO jobs VALUES (?,?,?)", (url, status, info))
    db.commit()


def process(key: str, csv_tags: list[str], load, cfg: dict, browser: Browser, categories: list[str]) -> str:
    """Pipeline d'un travail (URL du CSV ou fichier .md) : chargement, traduction, règles, brouillon, fiche de relecture."""
    url = key
    art = load()
    if len(art.text.split()) > cfg["llm"]["max_words"]:
        raise RuntimeError("Article trop long, à découper à la main")
    res = translate_article(art, cfg, browser, categories)
    tags = list(dict.fromkeys(csv_tags + res.tags))  # tags de la source ignorés : en anglais
    draft = backend(cfg).create_draft(cfg["wordpress"]["site"], res.title, res.html, tags,
                                      [res.category] if res.category else None, res.slug)
    res.warnings.extend(getattr(backend(cfg), "last_warnings", []))  # ex. étiquettes non posées (site restreint)
    write_review(Path("output/review") / f"{slug(label(key))}.md", art, res, draft)
    for w in res.warnings:
        log.warning("%s : %s", url, w)
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

    with Browser(cfg["llm"]["profile_dir"], cfg["llm"]["headless"]) as browser:
        for key, csv_tags, load in todo:
            try:
                draft = process(key, csv_tags, load, cfg, browser, categories)
                set_status(db, key, "published", draft)  # « published » = traité : un BROUILLON a été créé, jamais publié
                log.info("OK %s -> %s", key, draft)
            except Exception as e:
                set_status(db, key, "error", str(e))
                log.error("ECHEC %s : %s", key, e)

    names = {"published": "brouillon créé", "error": "erreur"}
    for key, status, info in db.execute("SELECT * FROM jobs"):
        print(f"[{names.get(status, status)}] {key} {info}")


if __name__ == "__main__":
    main()
