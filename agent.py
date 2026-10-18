"""Agent de traduction EN->FR : extraction, traduction via navigateur, brouillon WordPress.

Usage :
  python agent.py --login          # une fois : se connecter à Gemini/ChatGPT dans le profil
  python agent.py --auth           # une fois : autoriser l'accès WordPress.com
  python agent.py                  # traite urls.txt (les URLs déjà publiées sont sautées)
"""
import argparse
import logging
import sqlite3
import tomllib
from pathlib import Path

import wp
from extract import extract, read_csv
from llm_browser import Browser
from pipeline import slug, translate_article, write_review

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("agent.log", encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("agent")


def open_db() -> sqlite3.Connection:
    db = sqlite3.connect("state.db")
    db.execute("CREATE TABLE IF NOT EXISTS jobs (url TEXT PRIMARY KEY, status TEXT, info TEXT)")
    return db


def set_status(db, url, status, info=""):
    db.execute("INSERT OR REPLACE INTO jobs VALUES (?,?,?)", (url, status, info))
    db.commit()


def process(url: str, csv_tags: list[str], cfg: dict, browser: Browser, categories: list[str]) -> str:
    art = extract(url)
    if len(art.text.split()) > cfg["llm"]["max_words"]:
        raise RuntimeError("Article trop long, à découper à la main")
    res = translate_article(art, cfg, browser, categories)
    tags = list(dict.fromkeys(csv_tags + res.tags))  # tags de la source ignorés : en anglais
    draft = wp.create_draft(cfg["wordpress"]["site"], res.title, res.html, tags,
                            [res.category] if res.category else None, res.slug)
    write_review(Path("output/review") / f"{slug(url)}.md", art, res, draft)
    for w in res.warnings:
        log.warning("%s : %s", url, w)
    return draft


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--auth", action="store_true", help="autoriser WordPress.com (ID et secret saisis dans le terminal)")
    ap.add_argument("--csv", default="input/articles.csv", help="colonnes : url,tags (tags séparés par ;)")
    ap.add_argument("--force", action="store_true", help="retraite aussi les URLs déjà publiées (crée de nouveaux brouillons)")
    ap.add_argument("--only", type=int, default=None, help="ne traiter que la ligne N du CSV (1 = première), même si déjà publiée")
    args = ap.parse_args()

    cfg = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))

    if args.auth:
        import getpass

        wp.authorize(input("Client ID : ").strip(), getpass.getpass("Client secret (masqué) : ").strip())
        return
    if args.login:
        with Browser(cfg["llm"]["profile_dir"]) as b:
            b.login_session()
        return

    db = open_db()
    done = set() if args.force else {r[0] for r in db.execute("SELECT url FROM jobs WHERE status='published'")}
    todo = [(u, t) for i, (u, t) in enumerate(read_csv(args.csv), start=1)
            if (args.only is None or i == args.only) and (u not in done or args.only)]
    log.info("%d article(s) à traiter", len(todo))
    if not todo:
        return
    try:
        categories = wp.list_categories(cfg["wordpress"]["site"])
    except Exception as e:  # sans catégories, le LLM n'en propose pas ; l'article reste créé
        categories = []
        log.warning("Catégories du site illisibles (%s) : aucune catégorie ne sera proposée", e)

    with Browser(cfg["llm"]["profile_dir"], cfg["llm"]["headless"]) as browser:
        for url, csv_tags in todo:
            try:
                draft = process(url, csv_tags, cfg, browser, categories)
                set_status(db, url, "published", draft)
                log.info("OK %s -> %s", url, draft)
            except Exception as e:
                set_status(db, url, "error", str(e))
                log.error("ECHEC %s : %s", url, e)

    for url, status, info in db.execute("SELECT * FROM jobs"):
        print(f"[{status}] {url} {info}")


if __name__ == "__main__":
    main()
