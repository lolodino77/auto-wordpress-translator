"""Données de l'interface : articles à traduire (input/articles.csv + dossier input/articles_md/), résultats, réglages.

Les fichiers restent ceux de la ligne de commande : l'interface et `python agent.py` voient exactement la même liste."""
import csv
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

from extract import _front_matter, read_csv_rows
from pipeline import result_id

CSV_HEADER = ["url", "tags", "illustration"]
MD_FILENAME_MAX = 120


class StoreError(ValueError):
    """Erreur à afficher telle quelle à l'utilisateur (message en français simple)."""


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)

    # --- chemins ------------------------------------------------------------------------------------
    @property
    def csv_path(self) -> Path:
        return self.root / "input" / "articles.csv"

    @property
    def md_dir(self) -> Path:
        return self.root / "input" / "articles_md"

    @property
    def trash_dir(self) -> Path:
        return self.root / "input" / "corbeille"

    @property
    def results_dir(self) -> Path:
        return self.root / "output" / "results"

    # --- CSV ----------------------------------------------------------------------------------------
    def csv_rows(self) -> list[dict]:
        return read_csv_rows(str(self.csv_path)) if self.csv_path.exists() else []

    def _write_csv(self, rows: list[dict]) -> None:
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(CSV_HEADER)
            for r in rows:
                w.writerow([r["url"], ";".join(r["tags"]), r.get("illustration", "")])

    @staticmethod
    def _valid_url(url: str) -> bool:
        p = urlparse(url)
        return p.scheme in ("http", "https") and bool(p.netloc) and "." in p.netloc

    def add_urls(self, urls: list[str], tags: list[str], illustration: str) -> dict:
        rows = self.csv_rows()
        known = {r["url"].rstrip("/") for r in rows}
        added, duplicates, invalid = [], [], []
        for raw in urls:
            url = raw.strip()
            if not url:
                continue
            if not self._valid_url(url):
                invalid.append(url)
            elif url.rstrip("/") in known:
                duplicates.append(url)
            else:
                rows.append({"url": url, "tags": [t for t in tags if t], "illustration": illustration.strip()})
                known.add(url.rstrip("/"))
                added.append(url)
        if added:
            self._write_csv(rows)
        return {"added": added, "duplicates": duplicates, "invalid": invalid}

    # --- fichiers .md ---------------------------------------------------------------------------------
    def md_files(self) -> list[Path]:
        if not self.md_dir.is_dir():
            return []
        return sorted(self.md_dir.glob("*.md"), key=lambda p: p.name.lower())

    def save_md(self, filename: str, content: bytes) -> str:
        name = Path(filename).name  # jamais de chemin : seulement un nom de fichier
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", Path(name).stem).strip(" .")[:MD_FILENAME_MAX]
        if not stem:
            raise StoreError("Nom de fichier invalide.")
        if Path(name).suffix.lower() not in (".md", ".markdown", ".txt"):
            raise StoreError(f"« {name} » n'est pas un fichier texte .md.")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise StoreError(f"« {name} » n'est pas un fichier texte lisible (UTF-8).") from e
        if len(text.split()) < 50:
            raise StoreError(f"« {name} » contient trop peu de texte pour être un article.")
        self.md_dir.mkdir(parents=True, exist_ok=True)
        target, n = self.md_dir / f"{stem}.md", 2
        while target.exists():
            target, n = self.md_dir / f"{stem} ({n}).md", n + 1
        target.write_text(text, encoding="utf-8")
        return f"md:{target.name}"

    def _md_path(self, key: str) -> Path:
        name = key[3:]
        path = (self.md_dir / name).resolve()
        if path.parent != self.md_dir.resolve() or not path.exists():
            raise StoreError("Fichier introuvable.")
        return path

    def _md_meta(self, path: Path) -> dict:
        meta, _ = _front_matter(path.read_text(encoding="utf-8-sig"))
        return meta

    def _set_md_meta(self, path: Path, key: str, value: str) -> None:
        """Écrit (ou retire) une clé de l'en-tête « --- … --- » du fichier .md, sans toucher au texte de l'article."""
        raw = path.read_text(encoding="utf-8-sig")
        meta, body = _front_matter(raw)
        meta = {k: v for k, v in meta.items() if k != key}
        if value.strip():
            meta[key] = value.strip().replace("\n", " ")
        head = "".join(f"{k}: {v}\n" for k, v in meta.items())
        path.write_text((f"---\n{head}---\n" if head else "") + body.lstrip("\n"), encoding="utf-8")

    # --- liste commune --------------------------------------------------------------------------------
    def articles(self, statuses: dict[str, tuple[str, str]], results: dict[str, dict]) -> list[dict]:
        """Tous les articles (CSV puis fichiers), avec leur état : à traduire / brouillon créé / erreur."""
        items = []
        for i, r in enumerate(self.csv_rows(), start=1):
            items.append(self._item(r["url"], "url", r["url"], _title_from_url(r["url"]), r["tags"], r["illustration"],
                                    statuses, results))
        for p in self.md_files():
            meta = self._md_meta(p)
            items.append(self._item(f"md:{p.name}", "md", p.name, meta.get("title") or p.stem, [],
                                    meta.get("illustration", ""), statuses, results))
        return items

    @staticmethod
    def _item(key, kind, source, title, tags, illustration, statuses, results) -> dict:
        status, info = statuses.get(key, ("pending", ""))
        draft = results.get(result_id(key, "brouillon"))
        preview = results.get(result_id(key, "apercu"))
        return {
            "key": key, "kind": kind, "source": source, "title": title,
            "title_fr": (draft or preview or {}).get("title"),
            "tags": tags, "illustration": illustration,
            "status": {"published": "done", "error": "error"}.get(status, "pending"),
            "error": info if status == "error" else "",
            "draft_url": info if status == "published" else "",
            "result_id": draft["id"] if draft else None,
            "preview_id": preview["id"] if preview else None,
        }

    def update_article(self, key: str, tags: list[str] | None, illustration: str | None) -> None:
        if key.startswith("md:"):
            path = self._md_path(key)
            if illustration is not None:
                self._set_md_meta(path, "illustration", illustration)
            return
        rows = self.csv_rows()
        for r in rows:
            if r["url"] == key:
                if tags is not None:
                    r["tags"] = [t.strip() for t in tags if t.strip()]
                if illustration is not None:
                    r["illustration"] = illustration.strip()
                self._write_csv(rows)
                return
        raise StoreError("Article introuvable.")

    def delete_article(self, key: str) -> str:
        """Retire un article de la liste. Un fichier .md est déplacé dans input/corbeille/ (récupérable), jamais effacé."""
        if key.startswith("md:"):
            path = self._md_path(key)
            self.trash_dir.mkdir(parents=True, exist_ok=True)
            target, n = self.trash_dir / path.name, 2
            while target.exists():
                target, n = self.trash_dir / f"{path.stem} ({n}){path.suffix}", n + 1
            shutil.move(str(path), str(target))
            return f"Fichier déplacé dans input/corbeille/{target.name}"
        rows = self.csv_rows()
        kept = [r for r in rows if r["url"] != key]
        if len(kept) == len(rows):
            raise StoreError("Article introuvable.")
        self._write_csv(kept)
        return "Adresse retirée de la liste"

    # --- résultats ------------------------------------------------------------------------------------
    def results(self) -> dict[str, dict]:
        out = {}
        if self.results_dir.is_dir():
            for f in self.results_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    out[data["id"]] = data
                except (ValueError, KeyError):
                    continue
        return out

    def result(self, rid: str) -> dict:
        if not re.fullmatch(r"[a-z0-9-]+", rid):
            raise StoreError("Résultat introuvable.")
        f = self.results_dir / f"{rid}.json"
        if not f.exists():
            raise StoreError("Résultat introuvable.")
        return json.loads(f.read_text(encoding="utf-8"))


def _title_from_url(url: str) -> str:
    """Titre provisoire lisible avant traduction : le dernier segment de l'adresse, sans tirets."""
    p = urlparse(url)
    seg = [s for s in p.path.split("/") if s]
    words = re.sub(r"[-_]+", " ", seg[-1] if seg else p.netloc).strip()
    words = re.sub(r"\.(html?|php)$", "", words)
    return (words[:1].upper() + words[1:]) if words else url
