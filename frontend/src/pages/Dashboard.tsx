import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  CheckSquare,
  Clock,
  FileText,
  HeartPulse,
  Languages,
  ListChecks,
  Loader2,
  Sparkles,
  XCircle,
} from "lucide-react";
import { api, type ResultSummary } from "../api";
import { useApp } from "../context";
import { Postbox } from "../components";
import { ROLE_LABEL, engineName, formatDate, isGone, plural } from "../util";

export default function Dashboard() {
  const { status, run, account, startRun, version } = useApp();
  const [recent, setRecent] = useState<ResultSummary[] | null>(null);

  useEffect(() => {
    api.results().then((r) => setRecent(r.filter((x) => x.mode === "brouillon" && !isGone(x)).slice(0, 6))).catch(() => setRecent([]));
  }, [version]);

  const pending = status ? status.counts.pending + status.counts.error : 0;
  const running = !!status?.running;

  return (
    <>
      <h1 className="page-title">Tableau de bord</h1>

      <div className="welcome-panel">
        <div className="welcome-head">
          <h2>Bienvenue dans votre traducteur d'articles</h2>
          <p>
            Un article en anglais devient un brouillon en français sur <strong>{status?.site ?? "votre site"}</strong>, mis en
            page selon les consignes de la revue. Rien n'est jamais publié sans vous.
          </p>
          <Languages className="deco" aria-hidden />
        </div>
        <div className="welcome-cols">
          <div className="welcome-col">
            <div className="icon">
              <Sparkles />
            </div>
            <div>
              <h3>
                <span className="step-num">1.</span>Lancez la traduction
              </h3>
              <p>La traduction suit les consignes de la revue, puis le brouillon est créé dans WordPress.</p>
              {running ? (
                <Link to="/traduction" className="button button-primary">
                  <Loader2 className="spin" /> Suivre la traduction
                </Link>
              ) : (
                <button className="button button-primary" disabled={!pending} onClick={() => startRun({ mode: "brouillon" })}>
                  {pending ? `Traduire ${plural(pending, "article", "articles")}` : "Aucun article en attente"}
                </button>
              )}
              {!running && !pending && !!status?.counts.done && (
                <p className="description" style={{ marginTop: 8 }}>
                  Les articles de la liste ont déjà leur brouillon. Pour en refaire un :{" "}
                  <Link to="/articles?etat=done">« Retraduire »</Link>.
                </p>
              )}
            </div>
          </div>
          <div className="welcome-col">
            <div className="icon">
              <CheckSquare />
            </div>
            <div>
              <h3>
                <span className="step-num">2.</span>Relisez, puis publiez
              </h3>
              <p>Relisez la traduction et cochez les points à vérifier. La publication se fait vous-même, dans WordPress.</p>
              <Link to="/resultats" className="button">
                Voir les traductions
              </Link>
            </div>
          </div>
        </div>
      </div>

      <div className="dashboard-grid">
        <div>
          <Postbox title="D'un coup d'œil" icon={ListChecks}>
            {status ? (
              <ul className="glance">
                <li>
                  <Link to="/articles?etat=pending">
                    <Clock /> <strong>{status.counts.pending}</strong> à traduire
                  </Link>
                </li>
                <li>
                  <Link to="/articles?etat=done">
                    <CheckCircle2 /> <strong>{status.counts.done}</strong> {status.counts.done > 1 ? "brouillons créés" : "brouillon créé"}
                  </Link>
                </li>
                <li>
                  <Link to="/articles?etat=error">
                    <XCircle /> <strong>{status.counts.error}</strong> {status.counts.error > 1 ? "erreurs" : "erreur"}
                  </Link>
                </li>
                <li>
                  <Link to="/articles">
                    <FileText /> <strong>{status.total}</strong> au total
                  </Link>
                </li>
              </ul>
            ) : (
              <p className="muted">Chargement…</p>
            )}
          </Postbox>

          {run && run.status === "running" && (
            <Postbox title="Traduction en cours" icon={Loader2} actions={<Link to="/traduction">Suivre</Link>}>
              <div className="progress active">
                <div style={{ width: `${Math.max(4, ((run.done + run.errors) / run.total) * 100)}%` }} />
              </div>
              <p className="progress-label">
                {run.done + run.errors} sur {run.total} terminé{run.total > 1 ? "s" : ""}
              </p>
            </Postbox>
          )}

          <Postbox title="Activité récente" icon={Clock} actions={<Link to="/resultats">Tout voir</Link>}>
            {recent === null ? (
              <p className="muted">Chargement…</p>
            ) : recent.length === 0 ? (
              <p className="muted">Aucune traduction pour l'instant. Elles apparaîtront ici.</p>
            ) : (
              <ul className="activity">
                {recent.map((r) => (
                  <li key={r.id}>
                    <time>{formatDate(r.date)}</time>
                    <span>
                      {r.draft_url ? (
                        <a href={r.draft_url} target="_blank" rel="noreferrer">
                          {r.title}
                        </a>
                      ) : (
                        r.title
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Postbox>
        </div>

        <div>
          <Postbox title="Tout est prêt ?" icon={HeartPulse} actions={<Link to="/reglages">Réglages</Link>}>
            {status ? (
              <ul className="health">
                {accountHealth()}
                <li className={status.templates.ok ? "ok" : "bad"}>
                  {status.templates.ok ? <CheckCircle2 /> : <XCircle />}
                  <div className="grow">
                    <strong>Modèles de mise en page</strong>
                    {status.templates.ok
                      ? `${plural(status.templates.count, "modèle chargé", "modèles chargés")} (introduction, séparateurs, légende).`
                      : status.templates.error}
                  </div>
                </li>
                <li className={status.gemini_logged_in ? "ok" : "warn"}>
                  {status.gemini_logged_in ? <CheckCircle2 /> : <AlertTriangle />}
                  <div className="grow">
                    <strong>Compte Gemini</strong>
                    {status.gemini_logged_in ? (
                      "Connecté : les meilleurs modèles sont utilisés."
                    ) : (
                      <>
                        Non connecté : modèles limités, traductions moins bonnes. Fortement conseillé :{" "}
                        <Link to="/reglages">se connecter à Gemini</Link>.
                      </>
                    )}
                  </div>
                </li>
                <li className={status.chatgpt_logged_in ? "ok" : "warn"}>
                  {status.chatgpt_logged_in ? <CheckCircle2 /> : <AlertTriangle />}
                  <div className="grow">
                    <strong>Compte ChatGPT</strong>
                    {status.chatgpt_logged_in ? (
                      "Connecté : les meilleurs modèles sont utilisés."
                    ) : (
                      <>
                        Non connecté : usage limité, traductions plus lentes. Fortement conseillé :{" "}
                        <Link to="/reglages">se connecter à ChatGPT</Link>.
                      </>
                    )}
                  </div>
                </li>
                <li className={status.specs ? "ok" : "warn"}>
                  {status.specs ? <CheckCircle2 /> : <AlertTriangle />}
                  <div className="grow">
                    <strong>Consignes de traduction</strong>
                    {status.specs
                      ? `${plural(status.specs, "document PDF suivi", "documents PDF suivis")} à chaque traduction.`
                      : "Aucun document de consignes trouvé dans le dossier spec."}
                  </div>
                </li>
                <li className="ok">
                  <CheckCircle2 />
                  <div className="grow">
                    <strong>Traduction</strong>
                    {status.engines.map(engineName).join(", puis ")}
                    {status.engines.length > 1 ? " en relais si besoin." : "."}
                  </div>
                </li>
              </ul>
            ) : (
              <p className="muted">Chargement…</p>
            )}
            {account?.connected && <p className="description" style={{ marginTop: 10 }}>Compte vérifié auprès du site à l'ouverture de l'interface.</p>}
          </Postbox>
        </div>
      </div>
    </>
  );

  function accountHealth() {
    if (!status?.account_configured || account?.configured === false) {
      return (
        <li className="bad">
          <XCircle />
          <div className="grow">
            <strong>Compte WordPress</strong>
            Aucun compte enregistré : les brouillons ne peuvent pas encore être créés. <Link to="/reglages">Configurer le compte</Link>
          </div>
        </li>
      );
    }
    if (account?.connected === false) {
      return (
        <li className="bad">
          <XCircle />
          <div className="grow">
            <strong>Compte WordPress</strong>
            {account.error ?? "Le site refuse la connexion."} <Link to="/reglages">Vérifier le compte</Link>
          </div>
        </li>
      );
    }
    if (account?.connected) {
      const roles = (account.roles ?? []).map((r) => ROLE_LABEL[r] ?? r).join(", ");
      return (
        <li className={account.can_publish ? "warn" : "ok"}>
          {account.can_publish ? <AlertTriangle /> : <CheckCircle2 />}
          <div className="grow">
            <strong>Compte WordPress : {account.name || account.username}</strong>
            {roles && `Rôle : ${roles}. `}
            {account.can_publish ? "Attention : ce compte peut publier." : "Ne peut que créer des brouillons, jamais publier."}
          </div>
        </li>
      );
    }
    return (
      <li className="ok">
        <CheckCircle2 />
        <div className="grow">
          <strong>Compte WordPress</strong>
          Compte enregistré.
        </div>
      </li>
    );
  }
}
