import { useRef, useState, type DragEvent } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, FileUp, Image, Link2, ListPlus, Tag, XCircle } from "lucide-react";
import { api } from "../api";
import { errorText, useApp } from "../context";
import { Postbox, TagEditor } from "../components";
import { plural } from "../util";

export default function AddArticles() {
  const [tab, setTab] = useState<"url" | "file">("url");
  return (
    <>
      <h1 className="page-title">Ajouter des articles</h1>
      <p className="page-intro">
        Ajoutez des articles en anglais. Ils rejoignent la liste « Articles à traduire » ; la traduction se lance ensuite d'un clic.
      </p>
      <nav className="nav-tab-wrapper" role="tablist">
        <button role="tab" aria-selected={tab === "url"} className={"nav-tab" + (tab === "url" ? " nav-tab-active" : "")} onClick={() => setTab("url")}>
          <Link2 /> Par adresse web
        </button>
        <button role="tab" aria-selected={tab === "file"} className={"nav-tab" + (tab === "file" ? " nav-tab-active" : "")} onClick={() => setTab("file")}>
          <FileUp /> Par fichier .md
        </button>
      </nav>
      {tab === "url" ? <UrlForm /> : <FileForm />}
    </>
  );
}

function UrlForm() {
  const { notify, refresh, startRun, status } = useApp();
  const [text, setText] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [illustration, setIllustration] = useState("");
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<{ added: string[]; duplicates: string[]; invalid: string[] } | null>(null);
  // une adresse par ligne ; plusieurs adresses collées sur une même ligne (séparées par des espaces) sont aussi acceptées
  const urls = text.split(/\r?\n/).flatMap((line) => {
    const parts = line.trim().split(/\s+/).filter(Boolean);
    if (parts.length > 1 && parts.every((p) => /^https?:\/\//i.test(p))) return parts;
    return line.trim() ? [line.trim()] : [];
  });

  async function submit() {
    setBusy(true);
    try {
      const r = await api.addUrls(urls, tags, illustration);
      setLast(r);
      if (r.added.length) {
        setText("");
        setIllustration("");
        refresh();
      }
    } catch (e) {
      notify("error", errorText(e));
    }
    setBusy(false);
  }

  return (
    <div className="post-body">
      <div>
        <Postbox title="Adresses des articles (en anglais)" icon={Link2}>
          <label className="screen-reader-text" htmlFor="urls">
            Adresses
          </label>
          <textarea
            id="urls"
            className="big-textarea"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={"https://exemple.substack.com/p/un-article\nhttps://www.exemple.org/blog/un-autre-article"}
            spellCheck={false}
          />
          <p className="description">
            Une adresse par ligne. Vous pouvez en coller plusieurs d'un coup.{" "}
            {urls.length > 0 && <strong>{plural(urls.length, "adresse détectée", "adresses détectées")}.</strong>}
          </p>
        </Postbox>

        {last && (
          <>
            {last.added.length > 0 && (
              <div className="notice notice-success">
                <p>
                  <strong>{plural(last.added.length, "article ajouté", "articles ajoutés")} à la liste.</strong>
                </p>
                <div className="button-row">
                  {!status?.running && (
                    <button className="button button-primary" onClick={() => startRun({ keys: last.added, mode: "brouillon" })}>
                      {last.added.length > 1 ? "Les traduire maintenant" : "Le traduire maintenant"}
                    </button>
                  )}
                  <Link className="button" to="/articles">
                    Voir la liste
                  </Link>
                </div>
              </div>
            )}
            {last.duplicates.length > 0 && (
              <div className="notice notice-warning">
                <p>Déjà dans la liste (non ajouté{last.duplicates.length > 1 ? "s" : ""}) : {last.duplicates.join(", ")}</p>
              </div>
            )}
            {last.invalid.length > 0 && (
              <div className="notice notice-error">
                <p>
                  Adresse{last.invalid.length > 1 ? "s" : ""} non reconnue{last.invalid.length > 1 ? "s" : ""} (une adresse commence par
                  https://) : {last.invalid.join(", ")}
                </p>
              </div>
            )}
          </>
        )}
      </div>

      <div>
        <Postbox title="Ajouter à la liste" icon={ListPlus}>
          <p className="description" style={{ marginBottom: 12 }}>
            Les articles sont ajoutés à la liste sans être traduits tout de suite.
          </p>
          <button className="button button-primary" style={{ width: "100%" }} disabled={!urls.length || busy} onClick={submit}>
            {urls.length > 1 ? `Ajouter les ${urls.length} articles` : "Ajouter à la liste"}
          </button>
        </Postbox>
        <Postbox title="Étiquettes" icon={Tag}>
          <TagEditor tags={tags} onChange={setTags} />
          <p className="description">Facultatif. Ajoutées au brouillon, en plus de celles proposées par la traduction.</p>
        </Postbox>
        <Postbox title="Légende de l'illustration" icon={Image}>
          <input
            type="text"
            className="large-text"
            value={illustration}
            onChange={(e) => setIllustration(e.target.value)}
            placeholder="Ex. : Rembrandt, Le Retour du fils prodigue"
            aria-label="Légende de l'illustration"
          />
          <p className="description">Facultatif. Sans légende, le brouillon contient un repère « À COMPLÉTER ».</p>
        </Postbox>
      </div>
    </div>
  );
}

function FileForm() {
  const { notify, refresh, startRun, status } = useApp();
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<{ added: string[]; errors: string[] } | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function send(list: FileList | null) {
    const files = Array.from(list ?? []);
    if (!files.length) return;
    setBusy(true);
    try {
      const r = await api.addFiles(files);
      setReport(r);
      if (r.added.length) refresh();
    } catch (e) {
      notify("error", errorText(e));
    }
    setBusy(false);
    if (input.current) input.current.value = "";
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    send(e.dataTransfer.files);
  };

  return (
    <>
      <div
        className={"uploader" + (drag ? " drag" : "")}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
      >
        <h2>Déposez vos fichiers ici pour les ajouter</h2>
        <p>ou</p>
        <button className="button button-hero" onClick={() => input.current?.click()} disabled={busy}>
          {busy ? "Envoi…" : "Sélectionnez des fichiers"}
        </button>
        <input ref={input} type="file" multiple accept=".md,.markdown,.txt" hidden onChange={(e) => send(e.target.files)} />
        <p className="max-size">Fichiers texte Markdown (.md) ou .txt, 5 Mo maximum chacun.</p>
      </div>

      {report && (
        <div className="postbox" style={{ marginTop: 20 }}>
          <div className="inside">
            <ul className="upload-list">
              {report.added.map((k) => (
                <li key={k}>
                  <CheckCircle2 color="var(--green)" /> {k.replace(/^md:/, "")} : ajouté à la liste.
                </li>
              ))}
              {report.errors.map((m) => (
                <li key={m}>
                  <XCircle color="var(--red)" /> {m}
                </li>
              ))}
            </ul>
            {report.added.length > 0 && (
              <div className="button-row" style={{ marginTop: 12 }}>
                {!status?.running && (
                  <button className="button button-primary" onClick={() => startRun({ keys: report.added, mode: "brouillon" })}>
                    {report.added.length > 1 ? "Les traduire maintenant" : "Le traduire maintenant"}
                  </button>
                )}
                <Link className="button" to="/articles">
                  Voir la liste
                </Link>
              </div>
            )}
          </div>
        </div>
      )}

      <Postbox title="À quoi sert un fichier .md ?" className="md-help">
        <p>
          Certains sites empêchent la lecture automatique (article réservé aux abonnés, page protégée…). Dans ce cas, copiez le texte de
          l'article dans un éditeur de texte (Bloc-notes, TextEdit…) et enregistrez-le avec l'extension <code>.md</code>.
        </p>
        <p>Pour une traduction plus complète, vous pouvez commencer le fichier par ces lignes (toutes facultatives) :</p>
        <pre className="log-box" style={{ maxHeight: "none" }}>
          {"---\ntitle: Titre de l'article en anglais\nurl: https://adresse-de-l-article-original\nauthor: Nom de l'auteur\nillustration: Légende de l'image\n---\nTexte de l'article…"}
        </pre>
        <p className="description">
          Les titres de parties commencent par <code>#</code> ou <code>##</code>. Les notes de bas de page sont reconnues automatiquement.
        </p>
      </Postbox>
    </>
  );
}
