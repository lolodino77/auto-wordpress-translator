import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type ResultSummary } from "../api";
import { errorText, useApp } from "../context";
import { EXISTS_IN_WP, formatDate, isGone, plural, resultState } from "../util";

// Comme les listes de WordPress : « Toutes » n'inclut pas la corbeille, qui a son propre onglet.
type Filter = "all" | "brouillon" | "corbeille";

function matches(r: ResultSummary, f: Filter) {
  if (r.mode === "apercu") return false; // anciens essais : plus affichés
  if (f === "corbeille") return isGone(r);
  if (isGone(r)) return false;
  if (f === "brouillon") return r.mode === "brouillon" && EXISTS_IN_WP.has(r.wp_status ?? ""); // existence vérifiée
  return f === "all" || r.mode === f;
}

export default function Results() {
  const { version, notify, confirm, status } = useApp();
  const [items, setItems] = useState<ResultSummary[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");

  const load = useCallback(() => {
    api.results().then(setItems).catch((e) => notify("error", errorText(e)));
  }, [notify]);
  useEffect(load, [load, version]);

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: 0, brouillon: 0, corbeille: 0 };
    for (const r of items ?? []) for (const f of Object.keys(c) as Filter[]) if (matches(r, f)) c[f]++;
    return c;
  }, [items]);
  const shown = useMemo(() => {
    const n = q.trim().toLowerCase();
    return (items ?? []).filter((r) => matches(r, filter) && (!n || `${r.title} ${r.source_title}`.toLowerCase().includes(n)));
  }, [items, filter, q]);

  useEffect(() => {
    if (filter === "corbeille" && items && counts.corbeille === 0) setFilter("all");
  }, [filter, items, counts.corbeille]);

  async function archive(r: ResultSummary) {
    const ok = await confirm({
      title: "Retirer définitivement cette traduction de la liste ?",
      body: (
        <>
          <p>« {r.title} » ne s'affichera plus dans « Traductions faites ».</p>
          <p>Rien n'est modifié dans WordPress. Le fichier est rangé dans le dossier « output/results/retires » : vous pourrez le récupérer.</p>
        </>
      ),
      confirmLabel: "Retirer définitivement",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.archiveResult(r.id);
      notify("success", "Traduction retirée de la liste.");
      load();
    } catch (e) {
      notify("error", errorText(e));
    }
  }

  const tabs: { key: Filter; label: string }[] = [
    { key: "all", label: "Toutes" },
    { key: "brouillon", label: "Brouillons dans WordPress" },
    { key: "corbeille", label: "Corbeille" },
  ];

  return (
    <>
      <h1 className="page-title">Traductions faites</h1>
      <p className="page-intro">
        {filter === "corbeille"
          ? "Traductions dont le brouillon a été mis à la corbeille ou supprimé dans WordPress. Leurs articles sont redevenus « à traduire »."
          : "Cliquez sur un titre pour relire la traduction et cocher les points à vérifier avant de publier dans WordPress."}
      </p>
      {status?.drafts_check_error && (
        <div className="notice notice-warning">
          <p>
            <strong>L'état des brouillons n'a pas pu être vérifié dans WordPress</strong> ({status.drafts_check_error}). Les
            traductions concernées sont marquées « État non vérifié ».
          </p>
        </div>
      )}
      <ul className="subsubsub">
        {tabs
          .filter((t) => t.key !== "corbeille" || counts.corbeille > 0)
          .map((t) => (
            <li key={t.key}>
              <button className={filter === t.key ? "current" : ""} onClick={() => setFilter(t.key)} aria-current={filter === t.key}>
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
              <td colSpan={4}>Vérification de l'état des brouillons dans WordPress…</td>
            </tr>
          ) : shown.length === 0 ? (
            <tr className="empty">
              <td colSpan={4}>
                {items.length ? "Aucune traduction ne correspond." : "Aucune traduction pour l'instant. Elles apparaîtront ici à la fin de chaque traduction."}
              </td>
            </tr>
          ) : (
            shown.map((r) => {
              const gone = isGone(r);
              return (
                <tr key={r.id}>
                  <td>
                    <strong>
                      {r.draft_url && !gone ? (
                        <a className="row-title" href={r.draft_url} target="_blank" rel="noreferrer" title="Ouvrir le brouillon dans WordPress">
                          {r.title}
                        </a>
                      ) : (
                        <span className="row-title plain">{r.title}</span>
                      )}
                      <span className="post-state"> — {resultState(r).short}</span>
                    </strong>
                    <div className="row-actions">
                      {r.draft_url && !gone && (
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
                      {gone && (
                        <span className="delete">
                          <button onClick={() => archive(r)}>Retirer définitivement de la liste</button>
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
                    {resultState(r).long}
                    <br />
                    <span className="muted">{formatDate(r.date)}</span>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </>
  );
}
