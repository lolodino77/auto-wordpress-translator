"""Essai complet SANS publication : pour chaque article (URL du CSV ou fichier .md), charge, traduit, applique les règles
éditoriales et écrit output/NN-*.html (aperçu), output/NN-*.source.md et output/review/*.md (fiche de relecture).

Usage : python dry_run.py [--csv input/articles.csv | --md [input/articles_md]] [--engine gemini] [--only N]
"""
import argparse
import tomllib
import traceback
from pathlib import Path

from inputs import csv_jobs, label, md_jobs
from llm_browser import Browser
from pipeline import preview_html, slug, translate_article, write_review

ap = argparse.ArgumentParser()
ap.add_argument("--csv", default="input/articles.csv")
ap.add_argument("--md", nargs="?", const="input/articles_md", default=None, metavar="DOSSIER",
                help="au lieu du CSV, traite chaque fichier .md du dossier (défaut : input/articles_md)")
ap.add_argument("--engine", default=None, help="un seul moteur (sinon l'ordre de config.toml)")
ap.add_argument("--only", type=int, default=None, help="ne traiter que l'élément N de la liste (1 = premier)")
args = ap.parse_args()

cfg = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))
if args.engine:
    cfg["llm"]["engines"] = [args.engine]
out = Path("output")
out.mkdir(exist_ok=True)

jobs = md_jobs(args.md) if args.md is not None else csv_jobs(args.csv)
first_no = args.only or 1
if args.only:
    jobs = [jobs[args.only - 1]]

summary = []
with Browser(cfg["llm"]["profile_dir"]) as browser:
    for no, (key, csv_tags, load) in enumerate(jobs, start=first_no):
        print(f"\n[{no}] {label(key)}", flush=True)
        try:
            art = load()
            words = len(art.text.split())
            name = f"{no:02d}-{slug(label(key))}"
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
            summary.append((no, "OK", label(key), f"{len(res.fixes)} corr., {len(res.warnings)} avert."))
        except Exception as e:
            traceback.print_exc()
            summary.append((no, "ECHEC", label(key), str(e)[:120]))

print("\n===== RÉSUMÉ =====")
for no, status, name, info in summary:
    print(f"[{no}] {status:5s} {name} | {info}")
