"""Liste des travaux à traiter : soit les URLs du CSV, soit les fichiers .md d'un dossier. La pipeline (traduction puis
création du brouillon) est ensuite exactement la même.

Un travail = (clé, étiquettes demandées, fonction qui charge l'article). La clé identifie le travail dans la base d'état :
l'URL pour le CSV, « md:<nom du fichier> » pour un fichier."""
from pathlib import Path

from extract import Article, article_from_markdown, extract, read_csv_rows

Job = tuple[str, list[str], "callable[[], Article]"]


def _load_url(url: str, illustration: str) -> Article:
    art = extract(url)
    art.illustration = illustration  # légende fournie dans le CSV (vide = repère « À COMPLÉTER »)
    return art


def csv_jobs(path: str) -> list[Job]:
    return [(r["url"], r["tags"], (lambda u=r["url"], ill=r["illustration"]: _load_url(u, ill))) for r in read_csv_rows(path)]


def md_jobs(directory: str) -> list[Job]:
    d = Path(directory)
    if not d.is_dir():
        raise FileNotFoundError(f"Dossier introuvable : {d} (créez-le et déposez-y des fichiers .md)")
    files = sorted(d.glob("*.md"), key=lambda p: p.name.lower())
    return [(f"md:{p.name}", [], (lambda p=p: article_from_markdown(p))) for p in files]


def label(key: str) -> str:
    """Nom lisible d'un travail (sans le préfixe « md: »), pour les noms de fichiers de sortie."""
    return key[3:] if key.startswith("md:") else key
