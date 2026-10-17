"""Test rapide : envoie un court texte à chaque moteur (sans connexion si possible) et affiche le résultat."""
import sys
import tomllib
from pathlib import Path

from llm_browser import Browser, LLMUnavailable, parse_answer

cfg = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))
sample = (
    "Over the last two decades, it has become common to hear Christians speak approvingly "
    "of the collapse of cultural Christianity. But the phrase means different things depending on who says it."
)
prompt = cfg["llm"]["prompt"].format(title="Test article", text=sample)
engines = sys.argv[1:] or cfg["llm"]["engines"]

with Browser(cfg["llm"]["profile_dir"]) as b:
    for engine in engines:
        print(f"=== {engine} ===", flush=True)
        try:
            raw = b.translate(engine, prompt, timeout_s=180)
            title, tags, html = parse_answer(raw)
            print("TITRE:", title, "\nTAGS:", tags, "\nHTML:", html[:300], flush=True)
        except (LLMUnavailable, ValueError) as e:
            print("ECHEC:", e, flush=True)
