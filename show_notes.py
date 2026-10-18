"""Debug : affiche les appels de note et les notes détectés par l'extraction. Usage : python show_notes.py URL"""
import re
import sys

from extract import extract

a = extract(sys.argv[1])
print("appels :", sorted(set(re.findall(r"\[NOTE (\d+)\]", a.text)), key=int))
for m in re.finditer(r"(?m)^NOTE (\d+) : (.*)$", a.text):
    print(f"  NOTE {m.group(1)} : {m.group(2)[:140]}")
