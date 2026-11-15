import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Check, ChevronUp, Copy, ExternalLink, FileText, Languages, PanelRight, Send } from "lucide-react";
import { api, type Result } from "../api";
import { useApp } from "../context";
import { Notices } from "../components";
import { engineName, formatDate } from "../util";

// Styles du contenu affiché (dans un cadre isolé : le texte vient d'Internet, aucun script n'y est exécuté).
const FRAME_CSS = `
html { background: #fff; }
body { margin: 0; color: #1e1e1e; font: 19px/1.7 Georgia, "Times New Roman", serif; overflow-wrap: break-word; }
p { margin: 0 0 1.15em; }
h1, h2, h3, h4 { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.3; margin: 1.7em 0 .6em; }
h2 { font-size: 1.45em; } h3 { font-size: 1.2em; } h4 { font-size: 1.05em; }
a { color: #2271b1; }
hr { border: 0; border-top: 2px solid #ccc; margin: 2.2em auto; width: 100px; }
hr.is-style-wide { width: 100%; }
blockquote { margin: 1.5em 0; padding: 0 0 0 1.2em; border-left: 4px solid #1e1e1e; }
ul, ol { padding-left: 1.4em; margin: 0 0 1.15em; }
li { margin: .3em 0; }
.has-small-font-size { font-size: 15px; }
figure { margin: 1.5em 0; }
img { max-width: 100%; height: auto; }
mark.todo { background: #fcf0a3; padding: 0 3px; border-radius: 2px; font-family: -apple-system, sans-serif; font-size: .85em; font-weight: 600; }
span.fn { background: #eef4fb; border-radius: 2px; box-shadow: 0 0 0 1px #d5e5f5; }
`;

function decorate(html: string): string {
  return html
    .replace(/À COMPLÉTER/g, '<mark class="todo">À COMPLÉTER</mark>')
    .replace(/\[\[((?:(?!<\/p>)[\s\S])+?)\]\]/g, '<span class="fn" title="Note de bas de page">[[$1]]</span>');
}

function ContentFrame({ html }: { html: string }) {
  const ref = useRef<HTMLIFrameElement>(null);
  const observer = useRef<ResizeObserver>();
  const [height, setHeight] = useState(400);
  const doc = useMemo(
    () => `<!doctype html><html lang="fr"><head><meta charset="utf-8"><base target="_blank"><style>${FRAME_CSS}</style></head><body>${decorate(html)}</body></html>`,
    [html],
  );
  useEffect(() => () => observer.current?.disconnect(), []);
  const onLoad = () => {
    const d = ref.current?.contentDocument;
    if (!d?.body) return;
    const measure = () => setHeight(d.body.scrollHeight + 24);
    measure();
    observer.current?.disconnect();
    if ("ResizeObserver" in window) {
      observer.current = new ResizeObserver(measure);
      observer.current.observe(d.body);
    }
  };
  return (
    <iframe
      ref={ref}
      className="editor-frame"
      title="Contenu de l'article traduit"
      sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
      srcDoc={doc}
      onLoad={onLoad}
      style={{ height }}
    />
  );
}

function Panel({ title, children, open: initial = true }: { title: ReactNode; children: ReactNode; open?: boolean }) {
  const [open, setOpen] = useState(initial);
  return (
    <div className={"panel" + (open ? "" : " closed")}>
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span>{title}</span>
        <ChevronUp />
      </button>
      {open && <div className="panel-body">{children}</div>}
    </div>
  );
}

function useChecks(id: string) {
  const key = `awt-checks-${id}`;
  const [checked, setChecked] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(key) || "[]");
    } catch {
      return [];
    }
  });
  const toggle = (item: string) =>
    setChecked((c) => {
      const next = c.includes(item) ? c.filter((x) => x !== item) : [...c, item];
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        /* stockage indisponible : la case reste cochée jusqu'à la fermeture de la page */
      }
      return next;
    });
  return { checked, toggle };
}

function Checklist({ items, checked, toggle, prefix }: { items: string[]; checked: string[]; toggle: (s: string) => void; prefix: string }) {
  return (
    <ul className="checklist">
      {items.map((t, i) => {
        const on = checked.includes(t);
        return (
          <li key={t} className={on ? "checked" : ""}>
            <input id={`${prefix}-${i}`} type="checkbox" checked={on} onChange={() => toggle(t)} />
            <label htmlFor={`${prefix}-${i}`}>{t}</label>
          </li>
        );
      })}
    </ul>
  );
}

export default function Editor() {
  const { id = "" } = useParams();
  const { clearOldNotices } = useApp();
  const [res, setRes] = useState<Result | null>(null);
  const [error, setError] = useState("");

  useEffect(clearOldNotices, [id, clearOldNotices]);
  useEffect(() => {
    setRes(null);
    setError("");
    api.result(id).then(setRes).catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    document.title = res ? `${res.title} ‹ Traducteur` : "Traducteur d'articles";
    return () => {
      document.title = "Traducteur d'articles";
    };
  }, [res]);

  if (error)
    return (
      <div className="editor">
        <EditorHeader />
        <div className="editor-canvas">
          <div className="canvas-inner">
            <div className="notice notice-error">
              <p>{error}</p>
            </div>
            <Link to="/resultats">Retour aux traductions</Link>
          </div>
        </div>
      </div>
    );
  if (!res)
    return (
      <div className="editor">
        <EditorHeader />
        <div className="editor-canvas">
          <div className="canvas-inner muted">Chargement…</div>
        </div>
      </div>
    );
  return <EditorView res={res} />;
}

function EditorHeader({ children }: { children?: ReactNode }) {
  return (
    <header className="editor-header">
      <Link to="/resultats" className="editor-logo" aria-label="Retour aux traductions" title="Retour aux traductions">
        <Languages className="main" />
        <ArrowLeft className="back" />
      </Link>
      {children}
    </header>
  );
}

function EditorView({ res }: { res: Result }) {
  const { startRun, status } = useApp();
  const [view, setView] = useState<"visual" | "code">("visual");
  const [tab, setTab] = useState<"article" | "check">("article");
  const [sidebar, setSidebar] = useState(() => window.innerWidth > 782);
  const [copied, setCopied] = useState(false);
  const { checked, toggle } = useChecks(res.id);
  const isDraft = res.mode === "brouillon";
  const all = [...res.to_check, ...res.manual];
  const left = all.filter((t) => !checked.includes(t)).length;

  async function copy() {
    try {
      await navigator.clipboard.writeText(res.html);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = res.html;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="editor">
      <EditorHeader>
        <div className="editor-docbar" title={res.title}>
          <FileText size={16} />
          <span className="t">{res.title}</span>
          <span className="s">· {isDraft ? "Brouillon" : "Essai"}</span>
        </div>
        <div className="editor-actions">
          <div className="segmented" role="group" aria-label="Affichage">
            <button className={view === "visual" ? "on" : ""} onClick={() => setView("visual")}>
              Visuel
            </button>
            <button className={view === "code" ? "on" : ""} onClick={() => setView("code")}>
              Code HTML
            </button>
          </div>
          <button className="cbtn" onClick={copy} title="Copier le code HTML de l'article">
            {copied ? <Check /> : <Copy />}
            <span className="lbl">{copied ? "Copié !" : "Copier"}</span>
          </button>
          {res.draft_url ? (
            <a className="cbtn is-primary" href={res.draft_url} target="_blank" rel="noreferrer">
              <ExternalLink />
              <span className="lbl">Ouvrir dans WordPress</span>
            </a>
          ) : (
            <button
              className="cbtn is-primary"
              disabled={status?.running}
              onClick={() => startRun({ keys: [res.key], mode: "brouillon" })}
              title="Traduire à nouveau et créer le brouillon dans WordPress"
            >
              <Send />
              <span className="lbl">Créer le brouillon</span>
            </button>
          )}
          <button
            className={"cbtn icon" + (sidebar ? " is-pressed" : "")}
            onClick={() => setSidebar((s) => !s)}
            aria-pressed={sidebar}
            title="Réglages de l'article"
          >
            <PanelRight />
          </button>
        </div>
      </EditorHeader>

      <div className="editor-body">
        <div className="editor-canvas">
          <div style={{ maxWidth: 760, margin: "0 auto", padding: "0 32px" }}>
            <Notices />
          </div>
          {!isDraft && (
            <div className="preview-banner">
              <FileText size={16} /> Ceci est un essai : cette traduction n'a pas été envoyée à WordPress.
            </div>
          )}
          <div className="canvas-inner">
            {view === "visual" ? (
              <>
                <h1 className="editor-title">{res.title}</h1>
                <ContentFrame html={res.html} />
              </>
            ) : (
              <textarea className="code-view" readOnly value={res.html} onFocus={(e) => e.currentTarget.select()} aria-label="Code HTML" />
            )}
          </div>
        </div>

        {sidebar && (
          <aside className="editor-sidebar" aria-label="Réglages de l'article">
            <div className="sidebar-tabs" role="tablist">
              <button role="tab" aria-selected={tab === "article"} className={tab === "article" ? "on" : ""} onClick={() => setTab("article")}>
                Article
              </button>
              <button role="tab" aria-selected={tab === "check"} className={tab === "check" ? "on" : ""} onClick={() => setTab("check")}>
                À vérifier {left > 0 && <span className="count-bubble">{left}</span>}
              </button>
            </div>

            {tab === "article" ? (
              <>
                <div className="post-card">
                  <FileText />
                  <div>
                    <h3>{res.title}</h3>
                    <p>{isDraft ? "Brouillon créé dans WordPress, pas encore publié." : "Essai : pas encore dans WordPress."}</p>
                  </div>
                </div>
                <dl className="summary-rows">
                  <dt>Statut</dt>
                  <dd className="plain">{isDraft ? "Brouillon" : "Essai (non envoyé)"}</dd>
                  <dt>Identifiant (fin de l'adresse)</dt>
                  <dd className="plain">
                    <code>{res.slug || "—"}</code>
                  </dd>
                  <dt>Traduit le</dt>
                  <dd className="plain">{formatDate(res.date)}</dd>
                  <dt>Traduit par</dt>
                  <dd className="plain">{engineName(res.engine)}</dd>
                  {res.draft_url && (
                    <>
                      <dt>Dans WordPress</dt>
                      <dd>
                        <a href={res.draft_url} target="_blank" rel="noreferrer">
                          Ouvrir le brouillon
                        </a>
                      </dd>
                    </>
                  )}
                </dl>
                <Panel title="Catégories">{res.category ? <span className="chip">{res.category}</span> : <span>Aucune proposée : à choisir dans WordPress.</span>}</Panel>
                <Panel title="Étiquettes">
                  {res.tags.length ? (
                    <div className="chips">
                      {res.tags.map((t) => (
                        <span className="chip" key={t}>
                          {t}
                        </span>
                      ))}
                    </div>
                  ) : (
                    "Aucune."
                  )}
                </Panel>
                <Panel title="Article d'origine">
                  <p style={{ margin: "0 0 6px" }}>
                    {res.source_url ? (
                      <a href={res.source_url} target="_blank" rel="noreferrer">
                        {res.source_title || res.source_url}
                      </a>
                    ) : (
                      res.source_title
                    )}
                  </p>
                  {res.author && <p style={{ margin: 0, color: "#757575" }}>par {res.author}</p>}
                </Panel>
              </>
            ) : (
              <>
                <div style={{ padding: "16px 16px 0" }}>
                  <p className="check-progress">
                    {left === 0
                      ? "Tout est coché."
                      : `${all.length - left} point${all.length - left > 1 ? "s" : ""} coché${all.length - left > 1 ? "s" : ""} sur ${all.length}.`}{" "}
                    Les cases cochées sont mémorisées sur cet ordinateur.
                  </p>
                </div>
                <Panel title={`Signalé par la traduction (${res.to_check.length})`}>
                  {res.to_check.length ? (
                    <Checklist items={res.to_check} checked={checked} toggle={toggle} prefix="tc" />
                  ) : (
                    "Rien de signalé."
                  )}
                </Panel>
                <Panel title="Avant de publier dans WordPress">
                  <Checklist items={res.manual} checked={checked} toggle={toggle} prefix="mn" />
                </Panel>
                {res.warnings.length > 0 && (
                  <Panel title={`Avertissements (${res.warnings.length})`}>
                    <ul className="plain-list warn-list">
                      {res.warnings.map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  </Panel>
                )}
                <Panel title={`Corrections automatiques (${res.fixes.length})`} open={false}>
                  {res.fixes.length ? (
                    <ul className="plain-list">
                      {res.fixes.map((f, i) => (
                        <li key={i}>{f}</li>
                      ))}
                    </ul>
                  ) : (
                    "Aucune."
                  )}
                </Panel>
              </>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}
