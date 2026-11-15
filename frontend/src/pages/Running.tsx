import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Clock, ExternalLink, Eye, Loader2, MinusCircle, Sparkles, Square, XCircle } from "lucide-react";
import { api, type Article, type Run, type RunItem } from "../api";
import { useApp } from "../context";
import { Postbox } from "../components";
import { engineName, formatDuration, plural } from "../util";

export default function Running() {
  const { run, status, stopRun, version } = useApp();
  const [articles, setArticles] = useState<Record<string, Article>>({});
  const running = run?.status === "running";

  const load = useCallback(() => {
    api
      .articles()
      .then((list) => setArticles(Object.fromEntries(list.map((a) => [a.key, a]))))
      .catch(() => undefined);
  }, []);
  useEffect(load, [load, version]);
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(load, 4000);
    return () => window.clearInterval(t);
  }, [running, load]);

  return (
    <>
      <h1 className="page-title">Traduction</h1>
      {!run ? (
        <>
          <p className="page-intro">Aucune traduction n'a encore été lancée depuis l'ouverture du programme.</p>
          <StartPanel />
        </>
      ) : (
        <>
          <RunSummary run={run} onStop={stopRun} />
          {running && (
            <div className="notice notice-warning">
              <p>
                <strong>Une fenêtre de navigateur s'est ouverte pour la traduction : ne la fermez pas.</strong> Vous pouvez la réduire et
                continuer à utiliser votre ordinateur. Comptez environ une minute par article, parfois plus.
              </p>
            </div>
          )}
          {run.status === "error" && run.message && (
            <div className="notice notice-error">
              <p>
                <strong>La traduction s'est interrompue :</strong> {run.message}
              </p>
            </div>
          )}
          <Postbox title={run.mode === "apercu" ? "Articles (essai sans WordPress)" : "Articles"}>
            <ul className="run-items">
              {run.items.map((it) => (
                <RunRow key={it.key} item={it} mode={run.mode} article={articles[it.key]} engines={status?.engines ?? []} />
              ))}
            </ul>
          </Postbox>
          <details className="tech">
            <summary>Journal détaillé (pour les curieux)</summary>
            <pre className="log-box">{run.logs.length ? run.logs.join("\n") : "Rien pour l'instant."}</pre>
          </details>
          {!running && (
            <>
              <h2 className="section-title">Lancer une autre traduction</h2>
              <StartPanel />
            </>
          )}
        </>
      )}
    </>
  );
}

function RunSummary({ run, onStop }: { run: Run; onStop: () => void }) {
  const finished = run.done + run.errors + run.skipped;
  const pct = run.total ? (finished / run.total) * 100 : 0;
  const running = run.status === "running";
  const head = {
    running: { icon: <Loader2 className="spin" color="var(--blue)" />, text: "Traduction en cours…" },
    done: {
      icon: run.errors && !run.done ? <XCircle color="var(--red)" /> : <CheckCircle2 color="var(--green)" />,
      text: run.errors && !run.done ? "Traduction terminée, sans succès" : "Traduction terminée",
    },
    stopped: { icon: <MinusCircle color="var(--muted)" />, text: "Traduction arrêtée" },
    error: { icon: <XCircle color="var(--red)" />, text: "Traduction interrompue" },
  }[run.status];
  return (
    <div className="postbox" style={{ marginTop: 12 }}>
      <div className="inside">
        <div className="run-head">
          <div className="run-title">
            {head.icon}
            {head.text}
          </div>
          <div className="run-meta">
            {run.mode === "apercu" ? "Essai : rien n'est envoyé à WordPress" : "Les brouillons sont créés dans WordPress"} ·{" "}
            {formatDuration(run.seconds)}
          </div>
          {running && (
            <button className="button button-danger" onClick={onStop} disabled={run.stop_requested}>
              <Square /> {run.stop_requested ? "Arrêt après l'article en cours…" : "Arrêter après cet article"}
            </button>
          )}
        </div>
        <div className={"progress" + (running ? " active" : run.errors === 0 && run.done ? " ok" : "")}>
          <div style={{ width: `${running ? Math.max(3, pct) : pct}%` }} />
        </div>
        <div className="progress-label">
          {finished} sur {run.total} terminé{finished > 1 ? "s" : ""}
          {run.done > 0 && ` · ${plural(run.done, "réussi", "réussis")}`}
          {run.errors > 0 && ` · ${plural(run.errors, "erreur", "erreurs")}`}
        </div>
      </div>
    </div>
  );
}

const ICONS = {
  waiting: <Clock className="waiting" />,
  running: <Loader2 className="running spin" />,
  done: <CheckCircle2 className="done" />,
  error: <XCircle className="error" />,
  skipped: <MinusCircle className="waiting" />,
};

function RunRow({ item, mode, article, engines }: { item: RunItem; mode: Run["mode"]; article?: Article; engines: string[] }) {
  const steps: { key: RunItem["step"]; label: string }[] = [
    { key: "load", label: "Lecture de l'article" },
    { key: "translate", label: engines.length ? `Traduction par ${engineName(engines[0])}` : "Traduction" },
    ...(mode === "brouillon" ? [{ key: "publish" as const, label: "Création du brouillon" }] : []),
  ];
  const current = steps.findIndex((s) => s.key === item.step);
  const rid = mode === "brouillon" ? article?.result_id : article?.preview_id;
  const title = article ? article.title_fr || article.title : item.label;
  return (
    <li className="run-item">
      <div className="ri-icon">{ICONS[item.status]}</div>
      <div>
        <div className="ri-title">{title}</div>
        <div className="ri-sub">{item.label.replace(/^md:/, "Fichier ")}</div>
        {item.status !== "waiting" && item.status !== "skipped" && (
          <div className="steps">
            {steps.map((s, i) => {
              let cls = "";
              if (item.status === "done" || i < current) cls = "past";
              else if (i === current) cls = item.status === "error" ? "failed" : "now";
              return (
                <span key={s.key} style={{ display: "contents" }}>
                  {i > 0 && <span className="step-arrow">›</span>}
                  <span className={"step " + cls}>
                    {cls === "past" && <CheckCircle2 />}
                    {cls === "now" && <Loader2 className="spin" />}
                    {cls === "failed" && <XCircle />}
                    {s.label}
                  </span>
                </span>
              );
            })}
          </div>
        )}
        {item.status === "waiting" && <div className="ri-sub">En attente de son tour.</div>}
        {item.status === "error" && (
          <div className="row-error" style={{ fontSize: 13 }}>
            <XCircle /> {item.error}
          </div>
        )}
        {item.status === "done" && (
          <div className="ri-links">
            {rid && (
              <Link to={`/resultats/${rid}`}>
                <Eye /> Relire la traduction
              </Link>
            )}
            {item.draft_url && (
              <a href={item.draft_url} target="_blank" rel="noreferrer">
                <ExternalLink /> Ouvrir le brouillon dans WordPress
              </a>
            )}
          </div>
        )}
      </div>
      <div className="ri-time">{item.seconds > 0 && formatDuration(item.seconds)}</div>
    </li>
  );
}

function StartPanel() {
  const { status, startRun } = useApp();
  const pending = status ? status.counts.pending + status.counts.error : 0;
  return (
    <Postbox title="Lancer une traduction" icon={Sparkles}>
      {pending > 0 ? (
        <>
          <p>
            <strong>{plural(pending, "article attend", "articles attendent")} d'être traduit{pending > 1 ? "s" : ""}.</strong>
          </p>
          <div className="button-row">
            <button className="button button-primary button-hero" onClick={() => startRun({ mode: "brouillon" })}>
              Traduire et créer {pending > 1 ? "les brouillons" : "le brouillon"}
            </button>
            <button className="button button-hero" onClick={() => startRun({ mode: "apercu" })}>
              Faire un essai sans WordPress
            </button>
          </div>
          <p className="description" style={{ marginTop: 10 }}>
            L'essai traduit et met en page sans rien envoyer au site : pratique pour tester. Pour choisir certains articles seulement, cochez-les
            dans <Link to="/articles">la liste</Link> puis utilisez « Actions groupées ».
          </p>
        </>
      ) : (
        <>
          <p>Aucun article en attente de traduction.</p>
          <Link to="/ajouter" className="button button-primary">
            Ajouter des articles
          </Link>
        </>
      )}
    </Postbox>
  );
}
