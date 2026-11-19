import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Trash2, XCircle } from "lucide-react";
import { api, type Article } from "../api";
import { errorText, useApp } from "../context";
import { StatusBadge, TagEditor } from "../components";
import { plural, sourceLabel } from "../util";

type Filter = "all" | "pending" | "active" | "done" | "error";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "Tous" },
  { key: "pending", label: "À traduire" },
  { key: "active", label: "En cours" },
  { key: "done", label: "Brouillons créés" },
  { key: "error", label: "Erreurs" },
];

function matches(a: Article, f: Filter) {
  if (f === "all") return true;
  if (f === "active") return a.status === "queued" || a.status === "running";
  return a.status === f;
}

export default function Articles() {
  const { version, status, startRun, notify, confirm, refresh } = useApp();
  const [params, setParams] = useSearchParams();
  const filter = (params.get("etat") as Filter) || "all";
  const [items, setItems] = useState<Article[] | null>(null);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulk, setBulk] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const running = !!status?.running;

  const load = useCallback(() => {
    api.articles().then(setItems).catch((e) => notify("error", errorText(e)));
  }, [notify]);
  useEffect(load, [load, version]);
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(load, 3000);
    return () => window.clearInterval(t);
  }, [running, load]);

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: 0, pending: 0, active: 0, done: 0, error: 0 };
    for (const a of items ?? []) for (const f of FILTERS) if (matches(a, f.key)) c[f.key]++;
    return c;
  }, [items]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (items ?? []).filter(
      (a) =>
        matches(a, filter) &&
        (!needle || [a.title, a.title_fr ?? "", a.source, a.tags.join(" ")].some((s) => s.toLowerCase().includes(needle))),
    );
  }, [items, filter, q]);

  const setFilter = (f: Filter) => {
    setSelected(new Set());
    setParams(f === "all" ? {} : { etat: f });
  };
  const allChecked = shown.length > 0 && shown.every((a) => selected.has(a.key));
  const toggleAll = () => setSelected(allChecked ? new Set() : new Set(shown.map((a) => a.key)));
  const toggle = (k: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });

  const titleOf = (a: Article) => a.title_fr || a.title;

  async function retranslate(a: Article) {
    const ok = await confirm({
      title: "Retraduire cet article ?",
      body: (
        <p>
          Un brouillon existe déjà dans WordPress pour « {titleOf(a)} ». Une nouvelle traduction créera un <strong>second brouillon</strong>.
          L'ancien n'est ni modifié ni supprimé : vous pourrez le mettre à la corbeille vous-même dans WordPress.
        </p>
      ),
      confirmLabel: "Retraduire",
    });
    if (ok) startRun({ keys: [a.key], mode: "brouillon", force: true });
  }

  async function remove(list: Article[]) {
    const one = list.length === 1;
    const hasMd = list.some((a) => a.kind === "md");
    const hasDraft = list.some((a) => a.status === "done");
    const ok = await confirm({
      title: one ? "Retirer cet article de la liste ?" : `Retirer ${list.length} articles de la liste ?`,
      body: (
        <>
          <p>{one ? `« ${titleOf(list[0])} » ne sera plus proposé à la traduction.` : "Ils ne seront plus proposés à la traduction."}</p>
          {hasMd && <p>Les fichiers .md sont déplacés dans le dossier « input/corbeille » : vous pourrez les récupérer.</p>}
          {hasDraft && <p>Les brouillons déjà créés dans WordPress ne sont pas touchés.</p>}
        </>
      ),
      confirmLabel: "Retirer",
      danger: true,
    });
    if (!ok) return;
    let done = 0;
    for (const a of list) {
      try {
        await api.deleteArticle(a.key);
        done++;
      } catch (e) {
        notify("error", errorText(e));
      }
    }
    if (done) notify("success", one ? "Article retiré de la liste." : `${done} articles retirés de la liste.`);
    setSelected(new Set());
    refresh();
  }

  async function applyBulk() {
    const list = (items ?? []).filter((a) => selected.has(a.key));
    if (!bulk) return notify("warning", "Choisissez d'abord une action dans la liste « Actions groupées ».");
    if (!list.length) return notify("warning", "Cochez d'abord un ou plusieurs articles.");
    if (bulk === "remove") return remove(list);
    const todo = list.filter((a) => a.status !== "done");
    if (!todo.length) {
      const ok = await confirm({
        title: list.length > 1 ? `Retraduire ces ${list.length} articles ?` : "Retraduire cet article ?",
        body: (
          <p>
            {list.length > 1 ? "Ils ont" : "Il a"} déjà un brouillon dans WordPress. Une nouvelle traduction créera{" "}
            <strong>{list.length > 1 ? "de nouveaux brouillons" : "un nouveau brouillon"}</strong> ; les anciens ne sont ni modifiés ni
            supprimés (vous pourrez les mettre à la corbeille vous-même dans WordPress).
          </p>
        ),
        confirmLabel: "Retraduire",
      });
      if (ok) startRun({ keys: list.map((a) => a.key), mode: "brouillon", force: true });
      return;
    }
    if (todo.length < list.length)
      notify("info", `${plural(list.length - todo.length, "article ignoré", "articles ignorés")} : déjà un brouillon.`);
    startRun({ keys: todo.map((a) => a.key), mode: "brouillon" });
  }

  const pending = counts.pending + counts.error;

  return (
    <>
      <h1 className="page-title">Liste des articles à traduire</h1>
      <Link to="/ajouter" className="page-title-action">
        Ajouter des articles
      </Link>
      {pending > 0 && !running && (
        <div className="notice notice-info" style={{ marginTop: 12 }}>
          <p>
            <strong>{plural(pending, "article attend", "articles attendent")} d'être traduit{pending > 1 ? "s" : ""}.</strong>
          </p>
          <div className="button-row">
            <button className="button button-primary" onClick={() => startRun({ mode: "brouillon" })}>
              Traduire et créer {pending > 1 ? "les brouillons" : "le brouillon"}
            </button>
          </div>
        </div>
      )}
      {running && (
        <div className="notice notice-info" style={{ marginTop: 12 }}>
          <p>
            Une traduction est en cours. <Link to="/traduction">Suivre son avancement</Link>. Les modifications de la liste seront de
            nouveau possibles à la fin.
          </p>
        </div>
      )}

      <ul className="subsubsub">
        {FILTERS.filter((f) => f.key !== "active" || counts.active > 0).map((f) => (
          <li key={f.key}>
            <button className={filter === f.key ? "current" : ""} onClick={() => setFilter(f.key)} aria-current={filter === f.key}>
              {f.label} <span className="count">({counts[f.key]})</span>
            </button>
          </li>
        ))}
      </ul>

      <div className="tablenav">
        <label className="screen-reader-text" htmlFor="bulk">
          Actions groupées
        </label>
        <select id="bulk" value={bulk} onChange={(e) => setBulk(e.target.value)} disabled={running}>
          <option value="">Actions groupées</option>
          <option value="translate">Traduire et créer les brouillons</option>
          <option value="remove">Retirer de la liste</option>
        </select>
        <button className="button" onClick={applyBulk} disabled={running}>
          Appliquer
        </button>
        <span className="displaying-num">{plural(shown.length, "élément", "éléments")}</span>
        <div className="search-box">
          <label className="screen-reader-text" htmlFor="search">
            Rechercher
          </label>
          <input id="search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Titre, site, étiquette…" />
          <button className="button" onClick={() => setQ((x) => x.trim())}>
            Rechercher
          </button>
        </div>
      </div>

      <table className="list-table">
        <thead>
          <tr>
            <td className="check-column">
              <input type="checkbox" checked={allChecked} onChange={toggleAll} aria-label="Tout sélectionner" />
            </td>
            <th>Titre</th>
            <th className="col-source">Source</th>
            <th className="col-tags">Étiquettes</th>
            <th className="col-state">État</th>
          </tr>
        </thead>
        <tbody>
          {items === null ? (
            <tr className="empty">
              <td colSpan={5}>Chargement…</td>
            </tr>
          ) : items.length === 0 ? (
            <tr className="empty">
              <td colSpan={5}>
                Aucun article dans la liste pour l'instant. <Link to="/ajouter">Ajouter des articles</Link>
              </td>
            </tr>
          ) : shown.length === 0 ? (
            <tr className="empty">
              <td colSpan={5}>Aucun article ne correspond.</td>
            </tr>
          ) : (
            shown.map((a) =>
              editing === a.key ? (
                <QuickEdit
                  key={a.key}
                  article={a}
                  onClose={() => setEditing(null)}
                  onSaved={() => {
                    setEditing(null);
                    notify("success", "Article mis à jour.");
                    load();
                  }}
                />
              ) : (
                <tr key={a.key} className={selected.has(a.key) ? "selected" : ""}>
                  <th className="check-column" scope="row">
                    <input type="checkbox" checked={selected.has(a.key)} onChange={() => toggle(a.key)} aria-label={`Sélectionner ${titleOf(a)}`} />
                  </th>
                  <td>
                    <TitleCell a={a} />
                    <div className="row-actions">
                      {!running && (a.status === "pending" || a.status === "error") && (
                        <span>
                          <button onClick={() => startRun({ keys: [a.key], mode: "brouillon" })}>Traduire</button>
                        </span>
                      )}
                      {!running && a.status === "done" && (
                        <span>
                          <button onClick={() => retranslate(a)}>Retraduire</button>
                        </span>
                      )}
                      {a.draft_url && (
                        <span>
                          <a href={a.draft_url} target="_blank" rel="noreferrer">
                            Ouvrir dans WordPress
                          </a>
                        </span>
                      )}
                      {!running && (
                        <span>
                          <button onClick={() => setEditing(a.key)}>Modification rapide</button>
                        </span>
                      )}
                      {a.kind === "url" && (
                        <span>
                          <a href={a.source} target="_blank" rel="noreferrer">
                            Voir l'original
                          </a>
                        </span>
                      )}
                      {!running && (
                        <span className="delete">
                          <button onClick={() => remove([a])}>Retirer</button>
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="col-source">
                    {a.kind === "url" ? (
                      <a href={a.source} target="_blank" rel="noreferrer" title={a.source}>
                        {sourceLabel(a)}
                      </a>
                    ) : (
                      <span title={a.source}>{sourceLabel(a)}</span>
                    )}
                  </td>
                  <td className="col-tags tags-text">{a.tags.length ? a.tags.join(", ") : <span className="muted">—</span>}</td>
                  <td className="col-state">
                    <StatusBadge status={a.status} />
                  </td>
                </tr>
              ),
            )
          )}
        </tbody>
        <tfoot>
          <tr>
            <td className="check-column">
              <input type="checkbox" checked={allChecked} onChange={toggleAll} aria-label="Tout sélectionner" />
            </td>
            <th>Titre</th>
            <th className="col-source">Source</th>
            <th className="col-tags">Étiquettes</th>
            <th className="col-state">État</th>
          </tr>
        </tfoot>
      </table>
      <p className="footer-note">
        Astuce : passez la souris sur un titre pour voir les actions (Traduire, Modification rapide, Retirer…), comme dans WordPress.
      </p>
    </>
  );
}

function TitleCell({ a }: { a: Article }) {
  const title = a.title_fr || a.title;
  return (
    <Fragment>
      <strong>
        {a.draft_url ? (
          <a className="row-title" href={a.draft_url} target="_blank" rel="noreferrer" title="Ouvrir le brouillon dans WordPress">
            {title}
          </a>
        ) : (
          <span className="row-title plain">{title}</span>
        )}
        {a.status === "done" && <span className="post-state"> — Brouillon</span>}
      </strong>
      {a.title_fr && <div className="subtitle">Titre original : {a.title}</div>}
      {a.kind === "md" && <div className="subtitle">Fichier : {a.source}</div>}
      {a.note && (
        <div className="row-note">
          <Trash2 /> {a.note}
        </div>
      )}
      {a.status === "error" && a.error && (
        <div className="row-error">
          <XCircle /> {a.error}
        </div>
      )}
    </Fragment>
  );
}

function QuickEdit({ article, onClose, onSaved }: { article: Article; onClose: () => void; onSaved: () => void }) {
  const { notify } = useApp();
  const [tags, setTags] = useState<string[]>(article.tags);
  const [illustration, setIllustration] = useState(article.illustration);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      await api.editArticle(article.key, article.kind === "url" ? tags : null, illustration);
      onSaved();
    } catch (e) {
      notify("error", errorText(e));
      setBusy(false);
    }
  }

  return (
    <tr className="quick-edit">
      <td colSpan={5}>
        <h4>Modification rapide</h4>
        <p style={{ margin: "0 0 12px" }}>
          <strong>{article.title_fr || article.title}</strong>
        </p>
        <div className="qe-grid">
          <div>
            <label className="title" htmlFor="qe-tags">
              Étiquettes
            </label>
            {article.kind === "url" ? (
              <TagEditor id="qe-tags" tags={tags} onChange={setTags} />
            ) : (
              <p className="description">Pour un fichier .md, les étiquettes sont proposées par la traduction.</p>
            )}
          </div>
          <div>
            <label className="title" htmlFor="qe-ill">
              Légende de l'illustration
            </label>
            <input
              id="qe-ill"
              type="text"
              className="large-text"
              value={illustration}
              onChange={(e) => setIllustration(e.target.value)}
              placeholder="Ex. : Rembrandt, Le Retour du fils prodigue (vers 1668)"
            />
            <p className="description">Facultatif. Sans légende, le brouillon contient un repère « À COMPLÉTER ».</p>
          </div>
        </div>
        <div className="button-row">
          <button className="button button-primary" onClick={save} disabled={busy}>
            Mettre à jour
          </button>
          <button className="button" onClick={onClose} disabled={busy}>
            Annuler
          </button>
        </div>
      </td>
    </tr>
  );
}
