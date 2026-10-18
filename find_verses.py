"""Repère les articles du CSV qui contiennent des références bibliques (versets). Usage : python find_verses.py"""
import re

from extract import extract, read_csv

BOOKS = (r"Genesis|Gen|Exodus|Exod|Leviticus|Lev|Numbers|Num|Deuteronomy|Deut|Joshua|Josh|Judges|Judg|Ruth|"
         r"(?:1|2|I|II)\s?Samuel|(?:1|2)\s?Sam|(?:1|2|I|II)\s?Kings|(?:1|2)\s?Kgs|(?:1|2|I|II)\s?Chronicles|(?:1|2)\s?Chron|"
         r"Ezra|Nehemiah|Neh|Esther|Esth|Job|Psalms?|Ps|Proverbs|Prov|Ecclesiastes|Eccl|Song of Solomon|Song of Songs|"
         r"Isaiah|Isa|Jeremiah|Jer|Lamentations|Lam|Ezekiel|Ezek|Daniel|Dan|Hosea|Hos|Joel|Amos|Obadiah|Obad|Jonah|"
         r"Micah|Mic|Nahum|Nah|Habakkuk|Hab|Zephaniah|Zeph|Haggai|Hag|Zechariah|Zech|Malachi|Mal|Matthew|Matt|Mark|Luke|"
         r"John|Acts|Romans|Rom|(?:1|2|I|II)\s?Corinthians|(?:1|2)\s?Cor|Galatians|Gal|Ephesians|Eph|Philippians|Phil|"
         r"Colossians|Col|(?:1|2|I|II)\s?Thessalonians|(?:1|2)\s?Thess|(?:1|2|I|II)\s?Timothy|(?:1|2)\s?Tim|Titus|"
         r"Philemon|Hebrews|Heb|James|(?:1|2|I|II)\s?Peter|(?:1|2)\s?Pet|(?:1|2|3|I|II|III)\s?John|Jude|Revelation|Rev")
VERSE = re.compile(rf"\b(?:{BOOKS})\.?\s+\d{{1,3}}\s?:\s?\d{{1,3}}(?:\s?[–-]\s?\d{{1,3}})?")

for i, (url, _) in enumerate(read_csv("input/articles.csv"), start=1):
    text = extract(url).text
    refs = VERSE.findall(text)
    sample = ", ".join(dict.fromkeys(refs).keys())[:150]
    print(f"[{i}] {len(refs):3d} référence(s) | {url}\n      ex. : {sample or '-'}")
