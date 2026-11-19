import { useState } from "react";
import { Link } from "react-router-dom";
import { Image, Link2, ListPlus, Tag } from "lucide-react";
import { api, type AddUrlsResult } from "../api";
import { errorText, useApp } from "../context";
import { Postbox, TagEditor } from "../components";
import { plural } from "../util";

/** Ajouter un ou plusieurs articles à la liste, par leur adresse (comme « Ajouter un article » dans WordPress). */
export default function AddArticles() {
  const { notify, refresh, startRun, status, confirm } = useApp();
  const [text, setText] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [illustration, setIllustration] = useState("");
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<AddUrlsResult | null>(null);

  // une adresse par ligne ; plusieurs adresses collées sur une même ligne (séparées par des espaces) sont aussi acceptées
  const urls = text.split(/\r?\n/).flatMap((line) => {
    const parts = line.trim().split(/\s+/).filter(Boolean);
    if (parts.length > 1 && parts.every((p) => /^https?:\/\//i.test(p))) return parts;
    return line.trim() ? [line.trim()] : [];
  });
  const alreadyDone = new Set(last?.already_done.map((d) => d.url) ?? []);
  const fresh = last ? last.added.filter((u) => !alreadyDone.has(u)) : [];

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

  async function retranslate(keys: string[]) {
    const ok = await confirm({
      title: keys.length > 1 ? "Retraduire ces articles ?" : "Retraduire cet article ?",
      body: (
        <p>
          Un brouillon existe déjà dans WordPress. Une nouvelle traduction créera un <strong>nouveau brouillon</strong> ; l'ancien n'est ni
          modifié ni supprimé (vous pourrez le mettre à la corbeille vous-même dans WordPress).
        </p>
      ),
      confirmLabel: "Retraduire",
    });
    if (ok) startRun({ keys, mode: "brouillon", force: true });
  }

  return (
    <>
      <h1 className="page-title">Ajouter des articles</h1>
      <p className="page-intro">
        Collez l'adresse d'un ou de plusieurs articles en anglais. Ils rejoignent la liste des articles à traduire ; la traduction se lance
        ensuite d'un clic.
      </p>
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
              autoFocus
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
                    {!status?.running && fresh.length > 0 && (
                      <button className="button button-primary" onClick={() => startRun({ keys: fresh, mode: "brouillon" })}>
                        {fresh.length > 1 ? "Les traduire maintenant" : "Le traduire maintenant"}
                      </button>
                    )}
                    <Link className="button" to="/articles">
                      Voir la liste
                    </Link>
                  </div>
                </div>
              )}
              {last.already_done.length > 0 && (
                <div className="notice notice-warning">
                  <p>
                    <strong>
                      {last.already_done.length > 1 ? "Ces articles ont déjà été traduits" : "Cet article a déjà été traduit"} : un brouillon
                      existe déjà dans WordPress.
                    </strong>{" "}
                    {last.already_done.length > 1 ? "Ils ne sont donc pas comptés" : "Il n'est donc pas compté"} « à traduire ».
                  </p>
                  <ul style={{ margin: "0 0 8px 18px", padding: 0, listStyle: "disc" }}>
                    {last.already_done.map((d) => (
                      <li key={d.url} style={{ overflowWrap: "anywhere" }}>
                        {d.url} —{" "}
                        <a href={d.draft_url} target="_blank" rel="noreferrer">
                          ouvrir le brouillon existant
                        </a>
                      </li>
                    ))}
                  </ul>
                  {!status?.running && (
                    <div className="button-row">
                      <button className="button" onClick={() => retranslate(last.already_done.map((d) => d.url))}>
                        Retraduire quand même (nouveau brouillon)
                      </button>
                    </div>
                  )}
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
    </>
  );
}
