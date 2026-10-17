"""Essai complet SANS publication : pour chaque URL du CSV, extrait, traduit, écrit output/NN-*.html.

Usage : python dry_run.py [--csv input/articles.csv] [--engine gemini] [--only N]
"""
import argparse
import html as htmllib
import re
import tomllib
import traceback
from pathlib import Path

from extract import extract, read_csv
from llm_browser import Browser, LLMUnavailable, parse_answer

ap = argparse.ArgumentParser()
ap.add_argument("--csv", default="input/articles.csv")
ap.add_argument("--engine", default=None, help="un seul moteur (sinon l'ordre de config.toml)")
ap.add_argument("--only", type=int, default=None, help="ne traiter que la ligne N du CSV (1 = première)")
args = ap.parse_args()

cfg = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))
engines = [args.engine] if args.engine else cfg["llm"]["engines"]
out = Path("output")
out.mkdir(exist_ok=True)

rows = read_csv(args.csv)
if args.only:
    rows = [rows[args.only - 1]]
    first_no = args.only
else:
    first_no = 1

summary = []
with Browser(cfg["llm"]["profile_dir"]) as browser:
    for no, (url, csv_tags) in enumerate(rows, start=first_no):
        print(f"\n[{no}] {url}", flush=True)
        try:
            art = extract(url)
            words = len(art.text.split())
            slug = re.sub(r"[^a-z0-9]+", "-", url.rstrip("/").split("/")[-1].lower()).strip("-")[:50]
            (out / f"{no:02d}-{slug}.source.md").write_text(f"# {art.title}\n\n{art.text}", encoding="utf-8")
            print(f"    source : {art.title!r}, {words} mots", flush=True)
            if words > cfg["llm"]["max_words"]:
                raise RuntimeError(f"trop long ({words} mots)")
            prompt = cfg["llm"]["prompt"].format(title=art.title, text=art.text)
            for engine in engines:
                try:
                    title, tags, body = parse_answer(browser.translate(engine, prompt, timeout_s=600))
                    break
                except (LLMUnavailable, ValueError) as e:
                    print(f"    {engine} a échoué : {e}", flush=True)
            else:
                raise RuntimeError("tous les moteurs ont échoué")
            all_tags = list(dict.fromkeys(csv_tags + tags))  # tags de la source ignorés : en anglais
            (out / f"{no:02d}-{slug}.html").write_text(
                f"""<!doctype html><meta charset="utf-8"><title>{htmllib.escape(title)}</title>
<body style="max-width:46rem;margin:2rem auto;font:18px/1.6 Georgia,serif;padding:0 1rem">
<p style="color:#666;font:14px sans-serif">Tags : {htmllib.escape(', '.join(all_tags))} | {engine}</p>
<h1>{htmllib.escape(title)}</h1>
<p><em>Article original : <a href="{htmllib.escape(url)}">{htmllib.escape(art.title)}</a></em></p>
{body}""",
                encoding="utf-8",
            )
            n_fr = len(body.split())
            print(f"    traduction : {title!r}, {n_fr} mots ({n_fr / words:.0%} de la source), tags {all_tags}", flush=True)
            summary.append((no, "OK", url, f"{words} -> {n_fr} mots"))
        except Exception as e:
            traceback.print_exc()
            summary.append((no, "ECHEC", url, str(e)[:120]))

print("\n===== RÉSUMÉ =====")
for no, status, url, info in summary:
    print(f"[{no}] {status:5s} {url} | {info}")
