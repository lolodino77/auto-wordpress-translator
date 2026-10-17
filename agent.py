"""Agent de traduction EN->FR : extraction, traduction via navigateur, brouillon WordPress.

Usage :
  python agent.py --login          # une fois : se connecter à Gemini/ChatGPT dans le profil
  python agent.py --auth           # une fois : autoriser l'accès WordPress.com
  python agent.py                  # traite urls.txt (les URLs déjà publiées sont sautées)
"""
import argparse
import html as htmllib
import logging
import sqlite3
import tomllib
from pathlib import Path

import wp
from extract import extract, read_csv
from llm_browser import Browser, LLMUnavailable, parse_answer

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


def process(url: str, csv_tags: list[str], cfg: dict, browser: Browser) -> str:
    art = extract(url)
    if len(art.text.split()) > cfg["llm"]["max_words"]:
        raise RuntimeError("Article trop long, à découper à la main")
    prompt = cfg["llm"]["prompt"].format(title=art.title, text=art.text)

    errors = []
    for engine in cfg["llm"]["engines"]:
        try:
            raw = browser.translate(engine, prompt)
            title, tags, body = parse_answer(raw)
            break
        except (LLMUnavailable, ValueError) as e:
            log.warning("%s a échoué : %s", engine, e)
            errors.append(f"{engine}: {e}")
    else:
        raise RuntimeError("Tous les moteurs ont échoué : " + " | ".join(errors))

    source = f'<p><em>Article original : <a href="{htmllib.escape(url)}">{htmllib.escape(art.title)}</a></em></p>\n'
    all_tags = list(dict.fromkeys(csv_tags + tags))  # tags de la source ignorés : en anglais
    return wp.create_draft(cfg["wordpress"]["site"], title, source + body, all_tags)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--auth", action="store_true", help="autoriser WordPress.com (ID et secret saisis dans le terminal)")
    ap.add_argument("--csv", default="input/articles.csv", help="colonnes : url,tags (tags séparés par ;)")
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
    done = {r[0] for r in db.execute("SELECT url FROM jobs WHERE status='published'")}
    todo = [(u, t) for u, t in read_csv(args.csv) if u not in done]
    log.info("%d article(s) à traiter", len(todo))

    with Browser(cfg["llm"]["profile_dir"], cfg["llm"]["headless"]) as browser:
        for url, csv_tags in todo:
            try:
                draft = process(url, csv_tags, cfg, browser)
                set_status(db, url, "published", draft)
                log.info("OK %s -> %s", url, draft)
            except Exception as e:
                set_status(db, url, "error", str(e))
                log.error("ECHEC %s : %s", url, e)

    for url, status, info in db.execute("SELECT * FROM jobs"):
        print(f"[{status}] {url} {info}")


if __name__ == "__main__":
    main()
