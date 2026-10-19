"""Liste des travaux à traiter : soit les URLs du CSV, soit les fichiers .md d'un dossier. La pipeline (traduction puis
création du brouillon) est ensuite exactement la même.

Un travail = (clé, étiquettes demandées, fonction qui charge l'article). La clé identifie le travail dans la base d'état :
l'URL pour le CSV, « md:<nom du fichier> » pour un fichier."""
from pathlib import Path

from extract import Article, article_from_markdown, extract, read_csv

Job = tuple[str, list[str], "callable[[], Article]"]


def csv_jobs(path: str) -> list[Job]:
    return [(url, tags, (lambda u=url: extract(u))) for url, tags in read_csv(path)]


def md_jobs(directory: str) -> list[Job]:
    d = Path(directory)
    if not d.is_dir():
        raise FileNotFoundError(f"Dossier introuvable : {d} (créez-le et déposez-y des fichiers .md)")
    files = sorted(d.glob("*.md"), key=lambda p: p.name.lower())
    return [(f"md:{p.name}", [], (lambda p=p: article_from_markdown(p))) for p in files]


def label(key: str) -> str:
    """Nom lisible d'un travail (sans le préfixe « md: »), pour les noms de fichiers de sortie."""
    return key[3:] if key.startswith("md:") else key
