"""Teste l'extraction sur plusieurs URLs variées. Usage : python test_extract.py [url ...]"""
import sys

from extract import extract, read_csv

URLS = sys.argv[1:] or [url for url, _ in read_csv("input/articles.csv")]

for url in URLS:
    try:
        a = extract(url)
        words = len(a.text.split())
        print(f"OK   {words:6d} mots | {a.title[:60]!r} | début: {a.text[:70]!r} | fin: {a.text[-70:]!r}")
    except Exception as e:
        print(f"FAIL {url} -> {str(e)[:100]}")
