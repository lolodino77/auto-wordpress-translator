"""Test rapide : envoie un court texte à chaque moteur (sans connexion si possible) et affiche le résultat."""
import sys
import tomllib
from pathlib import Path

from extract import Article
from llm_browser import Browser, LLMUnavailable, parse_answer
from pipeline import make_prompt

cfg = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))
sample = (
    "Over the last two decades, it has become common to hear Christians speak approvingly "
    "of the collapse of cultural Christianity. But the phrase means different things depending on who says it."
)
prompt = make_prompt(Article("https://example.com/x", "Test article", sample), cfg, ["Théologie"])
engines = sys.argv[1:] or cfg["llm"]["engines"]

with Browser(cfg["llm"]["profile_dir"]) as b:
    for engine in engines:
        print(f"=== {engine} ===", flush=True)
        try:
            ans = parse_answer(b.translate(engine, prompt, timeout_s=180))
            print("TITRE:", ans.title, "\nTAGS:", ans.tags, "\nCATEGORIE:", ans.category,
                  "\nHTML:", ans.html[:300], "\nA VERIFIER:", ans.to_check, flush=True)
        except (LLMUnavailable, ValueError) as e:
            print("ECHEC:", e, flush=True)
