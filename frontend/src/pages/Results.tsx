import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ResultSummary } from "../api";
import { errorText, useApp } from "../context";
import { formatDate, plural } from "../util";

type Filter = "all" | "brouillon" | "apercu";

export default function Results() {
  const { version, notify } = useApp();
  const [items, setItems] = useState<ResultSummary[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");

  useEffect(() => {
    api.results().then(setItems).catch((e) => notify("error", errorText(e)));
  }, [version, notify]);

  const counts = useMemo(
    () => ({
      all: items?.length ?? 0,
      brouillon: items?.filter((r) => r.mode === "brouillon").length ?? 0,
      apercu: items?.filter((r) => r.mode === "apercu").length ?? 0,
    }),
    [items],
  );
  const shown = useMemo(() => {
    const n = q.trim().toLowerCase();
    return (items ?? []).filter(
      (r) => (filter === "all" || r.mode === filter) && (!n || `${r.title} ${r.source_title}`.toLowerCase().includes(n)),
    );
  }, [items, filter, q]);

  const tabs: { key: Filter; label: string }[] = [
    { key: "all", label: "Toutes" },
    { key: "brouillon", label: "Brouillons dans WordPress" },
    { key: "apercu", label: "Essais" },
  ];

  return (
    <>
      <h1 className="page-title">Traductions faites</h1>
      <p className="page-intro">
        Cliquez sur un titre pour relire la traduction et cocher les points à vérifier avant de publier dans WordPress.
      </p>
      <ul className="subsubsub">
        {tabs.map((t) => (
          <li key={t.key}>
            <button className={filter === t.key ? "current" : ""} onClick={() => setFilter(t.key)}>
              {t.label} <span className="count">({counts[t.key]})</span>
            </button>
          </li>
        ))}
      </ul>
      <div className="tablenav">
        <span className="displaying-num">{plural(shown.length, "élément", "éléments")}</span>
        <div className="search-box">
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher un titre…" aria-label="Rechercher" />
          <button className="button" onClick={() => setQ((x) => x.trim())}>
            Rechercher
          </button>
        </div>
      </div>
      <table className="list-table">
        <thead>
          <tr>
            <th>Titre</th>
            <th className="col-source">Article d'origine</th>
            <th className="col-small">À signaler</th>
            <th className="col-date">Date</th>
          </tr>
        </thead>
        <tbody>
          {items === null ? (
            <tr className="empty">
              <td colSpan={4}>Chargement…</td>
            </tr>
          ) : shown.length === 0 ? (
            <tr className="empty">
              <td colSpan={4}>
                {items.length ? "Aucune traduction ne correspond." : "Aucune traduction pour l'instant. Elles apparaîtront ici à la fin de chaque traduction."}
              </td>
            </tr>
          ) : (
            shown.map((r) => (
              <tr key={r.id}>
                <td>
                  <strong>
                    <Link className="row-title" to={`/resultats/${r.id}`}>
                      {r.title}
                    </Link>
                    <span className="post-state"> — {r.mode === "brouillon" ? "Brouillon" : "Essai"}</span>
                  </strong>
                  <div className="row-actions">
                    <span>
                      <Link to={`/resultats/${r.id}`}>Relire</Link>
                    </span>
                    {r.draft_url && (
                      <span>
                        <a href={r.draft_url} target="_blank" rel="noreferrer">
                          Ouvrir dans WordPress
                        </a>
                      </span>
                    )}
                    {r.source_url && (
                      <span>
                        <a href={r.source_url} target="_blank" rel="noreferrer">
                          Voir l'original
                        </a>
                      </span>
                    )}
                  </div>
                </td>
                <td className="col-source">{r.source_title}</td>
                <td className="col-small">
                  {r.warnings ? (
                    <span className="badge badge-error">{plural(r.warnings, "avertissement", "avertissements")}</span>
                  ) : (
                    <span className="badge badge-done">Rien de spécial</span>
                  )}
                </td>
                <td className="col-date">
                  {r.mode === "brouillon" ? "Brouillon créé" : "Essai"}
                  <br />
                  <span className="muted">{formatDate(r.date)}</span>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </>
  );
}
