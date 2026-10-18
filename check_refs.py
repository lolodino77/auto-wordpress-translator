"""Contrôle des références bibliques dans des brouillons WordPress (lecture seule). Usage : python check_refs.py ID [ID ...]"""
import html
import json
import re
import sys
import tomllib

import requests
import truststore

import bible

truststore.inject_into_ssl()
site = tomllib.loads(open("config.toml", encoding="utf-8").read())["wordpress"]["site"]
token = json.load(open("wp_token.json", encoding="utf-8"))["access_token"]
abbrevs = bible.load_abbreviations()
ABBR = "|".join(re.escape(a) for a in sorted(set(abbrevs.values()), key=len, reverse=True))
FULL = "|".join(re.escape(b) for b in sorted(bible.BOOKS, key=len, reverse=True))
EN = (r"Genesis|Gen|Exodus|Exod|Leviticus|Lev|Numbers|Deuteronomy|Deut|Joshua|Judges|Samuel|Kings|Chronicles|Psalms?|"
      r"Proverbs|Ecclesiastes|Isaiah|Isa|Jeremiah|Jer|Lamentations|Ezekiel|Daniel|Hosea|Jonah|Micah|Habakkuk|Malachi|"
      r"Matthew|Matt|Mark|Luke|John|Acts|Romans|Rom|Corinthians|Cor|Galatians|Gal|Ephesians|Eph|Philippians|Phil|"
      r"Colossians|Col|Thessalonians|Timothy|Titus|Hebrews|Heb|James|Peter|Jude|Revelation|Rev")
NUM = r"\d{1,3}\s?[,:.]\s?\d{1,3}(?:\s?[–-]\s?\d{1,3})?"

for pid in [a for a in sys.argv[1:] if a.isdigit()]:
    r = requests.get(f"https://public-api.wordpress.com/rest/v1.1/sites/{site}/posts/{pid}",
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    content = r.json()["content"]
    notes = re.findall(r"\[\[.*?\]\]", content, re.S)
    note_text = html.unescape(re.sub(r"<[^>]+>", "", " ".join(notes)))
    body_text = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"\[\[.*?\]\]", " ", content, flags=re.S)))
    full_ok = re.findall(rf"(?<![\w])(?:{FULL})\s\d{{1,3}},\d{{1,3}}", body_text)
    abbr_notes = re.findall(rf"(?<![\w])(?:{ABBR})\s\d{{1,3}},\d{{1,3}}", note_text)
    colon = re.findall(rf"[A-ZÉa-zé0-9 .]{{0,14}}\b\d{{1,3}}:\d{{1,3}}\b", html.unescape(re.sub(r"<[^>]+>", " ", content)))
    english = re.findall(rf"(?<![\w])(?:[123]\s)?(?:{EN})\.?\s{NUM}", body_text + " " + note_text)
    full_in_notes = re.findall(rf"(?<![\w])(?:{FULL})\s\d{{1,3}},\d{{1,3}}", note_text)
    print(f"=== Brouillon {pid} | {r.json()['title'][:60]}")
    print(f"  texte courant, nom complet + virgule : {len(full_ok)}  ex. {list(dict.fromkeys(full_ok))[:5]}")
    print(f"  notes, abréviation + virgule        : {len(abbr_notes)}  ex. {list(dict.fromkeys(abbr_notes))[:5]}")
    print(f"  notes, nom COMPLET (devrait être abrégé) : {len(full_in_notes)}  ex. {list(dict.fromkeys(full_in_notes))[:4]}")
    print(f"  forme avec deux-points restante     : {len(colon)}  ex. {[c.strip() for c in colon][:5]}")
    print(f"  nom de livre ANGLAIS restant        : {len(english)}  ex. {english[:5]}")
