"""Essai complet SANS publication : pour chaque URL du CSV, extrait, traduit, applique les règles éditoriales
et écrit output/NN-*.html (aperçu), output/NN-*.source.md et output/review/*.md (fiche de relecture).

Usage : python dry_run.py [--csv input/articles.csv] [--engine gemini] [--only N]
"""
import argparse
import tomllib
import traceback
from pathlib import Path

from extract import extract, read_csv
from llm_browser import Browser
from pipeline import preview_html, slug, translate_article, write_review

ap = argparse.ArgumentParser()
ap.add_argument("--csv", default="input/articles.csv")
ap.add_argument("--engine", default=None, help="un seul moteur (sinon l'ordre de config.toml)")
ap.add_argument("--only", type=int, default=None, help="ne traiter que la ligne N du CSV (1 = première)")
args = ap.parse_args()

cfg = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))
if args.engine:
    cfg["llm"]["engines"] = [args.engine]
out = Path("output")
out.mkdir(exist_ok=True)

rows = read_csv(args.csv)
first_no = args.only or 1
if args.only:
    rows = [rows[args.only - 1]]

summary = []
with Browser(cfg["llm"]["profile_dir"]) as browser:
    for no, (url, csv_tags) in enumerate(rows, start=first_no):
        print(f"\n[{no}] {url}", flush=True)
        try:
            art = extract(url)
            words = len(art.text.split())
            name = f"{no:02d}-{slug(url)}"
            (out / f"{name}.source.md").write_text(f"# {art.title}\n\n{art.text}", encoding="utf-8")
            print(f"    source : {art.title!r}, {words} mots", flush=True)
            if words > cfg["llm"]["max_words"]:
                raise RuntimeError(f"trop long ({words} mots)")
            res = translate_article(art, cfg, browser, categories=[])
            res.tags = list(dict.fromkeys(csv_tags + res.tags))
            (out / f"{name}.html").write_text(preview_html(art, res), encoding="utf-8")
            write_review(out / "review" / f"{name}.md", art, res)
            print(f"    traduction : {res.title!r}, tags {res.tags}", flush=True)
            print(f"    corrections auto : {len(res.fixes)} | avertissements : {len(res.warnings)} | à vérifier : {len(res.to_check)}", flush=True)
            summary.append((no, "OK", url, f"{len(res.fixes)} corr., {len(res.warnings)} avert."))
        except Exception as e:
            traceback.print_exc()
            summary.append((no, "ECHEC", url, str(e)[:120]))

print("\n===== RÉSUMÉ =====")
for no, status, url, info in summary:
    print(f"[{no}] {status:5s} {url} | {info}")
