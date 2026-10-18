"""Livres de la Bible (noms complets de la Segond 21 tels que listés sur universdelabible.net)
et mise en forme des références « Livre Chapitre,Verset »."""
import re
import tomllib
from pathlib import Path

BOOKS = [
    "Genèse", "Exode", "Lévitique", "Nombres", "Deutéronome", "Josué", "Juges", "Ruth",
    "1 Samuel", "2 Samuel", "1 Rois", "2 Rois", "1 Chroniques", "2 Chroniques", "Esdras",
    "Néhémie", "Esther", "Job", "Psaumes", "Proverbes", "Ecclésiaste", "Cantique des Cantiques",
    "Esaïe", "Jérémie", "Lamentations", "Ezéchiel", "Daniel", "Osée", "Joël", "Amos", "Abdias",
    "Jonas", "Michée", "Nahum", "Habakuk", "Sophonie", "Aggée", "Zacharie", "Malachie",
    "Matthieu", "Marc", "Luc", "Jean", "Actes", "Romains", "1 Corinthiens", "2 Corinthiens",
    "Galates", "Ephésiens", "Philippiens", "Colossiens", "1 Thessaloniciens", "2 Thessaloniciens",
    "1 Timothée", "2 Timothée", "Tite", "Philémon", "Hébreux", "Jacques", "1 Pierre", "2 Pierre",
    "1 Jean", "2 Jean", "3 Jean", "Jude", "Apocalypse",
]

# Autres graphies courantes -> graphie de la liste ci-dessus
VARIANTS = {
    "Ésaïe": "Esaïe", "Isaïe": "Esaïe", "Ézéchiel": "Ezéchiel", "Habacuc": "Habakuk",
    "Éphésiens": "Ephésiens", "Cantique des cantiques": "Cantique des Cantiques",
    "Qohéleth": "Ecclésiaste",
}

# Abréviations : fichier bible_abbreviations.toml. Convention retenue = convention universitaire de la Bible de
# Jérusalem (Gn, Rm, Jn, 1 Co…), d'après le tableau de J.-P. Lacroux, Orthotypographie, « Abréviation des livres
# bibliques » (colonne « Jérus. »). Il n'existe pas de norme unique ; la page Segond 21 de la spec ne donne que les
# noms complets. Le fichier se modifie librement (valeur vide = nom complet conservé).
ABBREV_FILE = Path("bible_abbreviations.toml")


def load_abbreviations(path: Path = ABBREV_FILE) -> dict[str, str]:
    """Abréviations fournies par l'utilisateur (nom complet -> abréviation). Les valeurs vides sont ignorées."""
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if v}


def _name_pattern(name: str) -> str:
    return re.escape(name).replace(r"\ ", r"[  ]")


_ALL = {**{b: b for b in BOOKS}, **VARIANTS}
_REF = re.compile(
    r"(?<![\w])(" + "|".join(_name_pattern(n) for n in sorted(_ALL, key=len, reverse=True)) + r")"
    r"[  ]+(\d{1,3})[ ]?[:,.][ ]?(\d{1,3})(?!\d)"
)
_NAME_BY_PATTERN = {n.replace(" ", " "): _ALL[n] for n in _ALL} | _ALL


def normalize_refs(text: str, abbreviate: bool, abbrevs: dict[str, str]) -> tuple[str, int, bool]:
    """Met les références au format « Livre Chapitre,Verset » ; abrège le nom du livre si demandé et possible.

    Retourne (texte, nombre de références modifiées, abréviation manquante)."""
    changed = 0
    missing = False

    def sub(m: re.Match) -> str:
        nonlocal changed, missing
        book = _NAME_BY_PATTERN[m.group(1)]
        name = book
        if abbreviate:
            if abbrevs.get(book):
                name = abbrevs[book]
            else:
                missing = True
        new = f"{name} {m.group(2)},{m.group(3)}"
        if new != m.group(0):
            changed += 1
        return new

    return _REF.sub(sub, text), changed, missing
