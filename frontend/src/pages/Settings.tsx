import { useEffect, useState, type FormEvent } from "react";
import { ArrowDown, ArrowUp, CheckCircle2, XCircle } from "lucide-react";
import { api, type GeminiStatus, type Settings } from "../api";
import { errorText, useApp } from "../context";
import { InlineNotice } from "../components";
import { ENGINE_LABEL, ROLE_LABEL } from "../util";

const ALL_ENGINES = ["gemini", "gpt"];

export default function SettingsPage() {
  const { notify, refresh, refreshAccount, status } = useApp();
  const [loaded, setLoaded] = useState<Settings | null>(null);
  const [engines, setEngines] = useState<{ id: string; on: boolean }[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .settings()
      .then((s) => {
        setLoaded(s);
        setEngines([...s.engines.map((id) => ({ id, on: true })), ...ALL_ENGINES.filter((e) => !s.engines.includes(e)).map((id) => ({ id, on: false }))]);
      })
      .catch((e) => notify("error", errorText(e)));
  }, [notify]);

  const move = (i: number, d: -1 | 1) =>
    setEngines((list) => {
      const n = [...list];
      [n[i], n[i + d]] = [n[i + d], n[i]];
      return n;
    });

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.saveSettings({ engines: engines.filter((x) => x.on).map((x) => x.id) });
      notify("success", "Réglages enregistrés.");
      refresh();
      refreshAccount();
    } catch (err) {
      notify("error", errorText(err));
    }
    setBusy(false);
  }

  let rank = 0;
  return (
    <>
      <h1 className="page-title">Réglages</h1>
      {!loaded ? (
        <p className="muted">Chargement…</p>
      ) : (
        <>
          <form onSubmit={save}>
            <h2 className="section-title">Traduction</h2>
            <table className="form-table" role="presentation">
              <tbody>
                <tr>
                  <th scope="row">Outils de traduction</th>
                  <td>
                    <ul className="engine-list">
                      {engines.map((e, i) => (
                        <li key={e.id}>
                          <span className={"rank" + (e.on ? "" : " off")}>{e.on ? ++rank : "–"}</span>
                          <label className="check grow">
                            <input
                              type="checkbox"
                              checked={e.on}
                              onChange={() => setEngines((l) => l.map((x) => (x.id === e.id ? { ...x, on: !x.on } : x)))}
                            />
                            {ENGINE_LABEL[e.id] ?? e.id}
                          </label>
                          <button type="button" className="icon-btn" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Monter">
                            <ArrowUp />
                          </button>
                          <button type="button" className="icon-btn" disabled={i === engines.length - 1} onClick={() => move(i, 1)} aria-label="Descendre">
                            <ArrowDown />
                          </button>
                        </li>
                      ))}
                    </ul>
                    <p className="description">
                      Le premier est essayé d'abord ; le suivant prend le relais s'il est indisponible. Tous deux sont utilisés gratuitement,
                      dans une fenêtre de navigateur.
                    </p>
                  </td>
                </tr>
                {loaded.max_words && (
                  <tr>
                    <th scope="row">Longueur maximale</th>
                    <td>
                      <InlineNotice kind="warn">
                        <strong>{loaded.max_words.toLocaleString("fr-FR")} mots par article</strong> (environ{" "}
                        {Math.round(loaded.max_words / 500)} pages). Au-delà, l'outil de traduction risque de couper ou de raccourcir le texte :
                        l'article est alors refusé et il faut le <strong>découper à la main</strong> avant de le traduire.
                      </InlineNotice>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            <p className="submit">
              <button type="submit" className="button button-primary" disabled={busy || !engines.some((e) => e.on)}>
                Enregistrer les modifications
              </button>
            </p>
          </form>

          <GeminiSection />

          <AccountSection mode={loaded.mode} site={status?.site ?? loaded.site} />
        </>
      )}
    </>
  );
}

function AccountSection({ mode, site }: { mode: Settings["mode"]; site: string }) {
  const { account, notify, refresh, refreshAccount } = useApp();
  const [user, setUser] = useState("");
  const [pwd, setPwd] = useState("");
  const [busy, setBusy] = useState(false);
  const [change, setChange] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const a = await api.saveAccount(user, pwd);
      setPwd("");
      setChange(false);
      notify("success", `Compte vérifié et enregistré : ${a.name || a.username}.`);
      refreshAccount();
      refresh();
    } catch (err) {
      notify("error", errorText(err));
    }
    setBusy(false);
  }

  const roles = (account?.roles ?? []).map((r) => ROLE_LABEL[r] ?? r).join(", ");
  const showForm = mode === "selfhosted" && (change || !account?.configured || account?.connected === false);

  return (
    <>
      <h2 className="section-title">Compte utilisé pour créer les brouillons</h2>
      <p className="page-intro">
        Le programme se connecte à {site} avec un compte dédié et un « mot de passe d'application ». Conseillé : un compte au rôle{" "}
        <strong>Contributeur</strong>, qui peut créer des brouillons mais jamais publier.
      </p>

      {account === null ? (
        <p className="muted">Vérification du compte auprès du site…</p>
      ) : account.connected ? (
        <div className="postbox" style={{ maxWidth: 640 }}>
          <div className="inside">
            <InlineNotice kind={account.can_publish ? "warn" : "ok"}>
              Connecté en tant que <strong>{account.name || account.username}</strong>
              {account.username && account.name && account.name !== account.username && <> (identifiant : {account.username})</>}
              {roles && <> — rôle : {roles}</>}.
            </InlineNotice>
            <ul className="rights">
              <Right ok={!!account.can_create} text={account.can_create ? "Peut créer des brouillons" : "Ne peut pas créer de brouillons"} />
              <Right ok={!account.can_publish} text={account.can_publish ? "PEUT publier (déconseillé : préférez un compte Contributeur)" : "Ne peut pas publier"} />
              <Right ok={!account.can_edit_others} text={account.can_edit_others ? "Peut modifier les articles des autres" : "Ne peut pas modifier les articles des autres"} />
              <Right ok={!account.can_delete_others} text={account.can_delete_others ? "Peut supprimer les articles des autres" : "Ne peut pas supprimer les articles des autres"} />
            </ul>
            {mode === "selfhosted" && !change && (
              <p style={{ margin: "12px 0 0" }}>
                <button className="button" onClick={() => setChange(true)}>
                  Changer de compte
                </button>
              </p>
            )}
          </div>
        </div>
      ) : account.configured && account.connected === false ? (
        <InlineNotice kind="bad">{account.error ?? "Le site refuse la connexion avec le compte enregistré."}</InlineNotice>
      ) : mode === "wpcom" && account.configured ? (
        <InlineNotice kind="ok">Autorisation WordPress.com enregistrée.</InlineNotice>
      ) : (
        <InlineNotice kind="warn">Aucun compte enregistré : les brouillons ne peuvent pas encore être créés.</InlineNotice>
      )}

      {mode === "wpcom" && (
        <div style={{ marginTop: 12 }}>
          <InlineNotice kind="info">
            Pour un site WordPress.com, l'autorisation se fait une seule fois dans un terminal, avec la commande <code>python agent.py --auth</code>.
          </InlineNotice>
        </div>
      )}

      {showForm && (
        <form onSubmit={submit} autoComplete="off">
          <table className="form-table" role="presentation">
            <tbody>
              <tr>
                <th scope="row">
                  <label htmlFor="wp-user">Identifiant WordPress</label>
                </th>
                <td>
                  <input id="wp-user" type="text" className="regular-text" value={user} onChange={(e) => setUser(e.target.value)} autoComplete="off" spellCheck={false} />
                  <p className="description">Le nom d'utilisateur du compte dédié à la traduction.</p>
                </td>
              </tr>
              <tr>
                <th scope="row">
                  <label htmlFor="wp-pass">Mot de passe d'application</label>
                </th>
                <td>
                  <input id="wp-pass" type="password" className="regular-text" value={pwd} onChange={(e) => setPwd(e.target.value)} autoComplete="new-password" spellCheck={false} />
                  <p className="description">
                    Ce n'est pas le mot de passe habituel du compte. Il est vérifié auprès du site puis enregistré uniquement sur cet ordinateur.
                  </p>
                  <details style={{ marginTop: 10 }}>
                    <summary className="button-link" style={{ cursor: "pointer" }}>
                      Comment obtenir un mot de passe d'application ?
                    </summary>
                    <ol style={{ margin: "10px 0 0", paddingLeft: 20 }}>
                      <li>Connectez-vous à l'administration de {site} (…/wp-admin) avec le compte prévu pour la traduction.</li>
                      <li>
                        Ouvrez le menu <strong>Comptes</strong>, puis descendez jusqu'à « Mots de passe d'application ».
                      </li>
                      <li>
                        Donnez un nom (par exemple « Traducteur ») et cliquez sur <strong>Ajouter un mot de passe d'application</strong>.
                      </li>
                      <li>Copiez le mot de passe affiché (4 lettres, espace, 4 lettres…) et collez-le ici.</li>
                    </ol>
                  </details>
                </td>
              </tr>
            </tbody>
          </table>
          <p className="submit button-row">
            <button type="submit" className="button button-primary" disabled={busy || !user.trim() || !pwd.trim()}>
              {busy ? "Vérification…" : "Vérifier et enregistrer"}
            </button>
            {change && (
              <button type="button" className="button" onClick={() => setChange(false)}>
                Annuler
              </button>
            )}
          </p>
        </form>
      )}
    </>
  );
}

function GeminiSection() {
  const { notify, refresh } = useApp();
  const [st, setSt] = useState<GeminiStatus | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => api.gemini().then((s) => alive && setSt(s)).catch(() => undefined);
    load();
    const t = window.setInterval(load, 2000); // suit la fenêtre de connexion pendant qu'elle est ouverte
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, []);

  useEffect(() => {
    if (st && !st.window_open) refresh(); // met à jour le tableau de bord quand la fenêtre se ferme
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [st?.window_open]);

  async function open() {
    try {
      setSt(await api.geminiLogin());
    } catch (e) {
      notify("error", errorText(e));
    }
  }

  async function done() {
    await api.geminiClose().catch(() => undefined);
  }

  return (
    <>
      <h2 className="section-title">Compte Gemini (facultatif, fortement conseillé)</h2>
      <p className="page-intro">
        Sans compte, Gemini ne donne accès qu'à ses modèles les plus limités : traductions moins bonnes et refus plus fréquents
        (« Cela dépasse mes capacités »). Avec un compte Google (gratuit), il utilise de bien meilleurs modèles. La connexion se fait
        une seule fois : Gemini s'en souvient ensuite. Le programme ne voit jamais votre mot de passe Google.
      </p>
      <div className="postbox" style={{ maxWidth: 640 }}>
        <div className="inside">
          {st === null ? (
            <p className="muted">Vérification…</p>
          ) : st.window_open ? (
            <>
              <InlineNotice kind="info">
                <strong>Une fenêtre Chrome est ouverte sur Gemini.</strong> Cliquez sur « Se connecter » en haut à droite de Gemini et entrez
                votre compte Google. Une fois connecté, fermez cette fenêtre Chrome (ou cliquez sur « C'est fait » ci-dessous) : la connexion est
                alors vérifiée.
              </InlineNotice>
              <p style={{ margin: "12px 0 0" }}>
                {st.logged_in ? (
                  <strong style={{ color: "var(--green)" }}>✓ Connexion détectée.</strong>
                ) : (
                  <span className="muted">La connexion sera vérifiée à la fermeture de la fenêtre.</span>
                )}{" "}
                <button className="button button-primary" onClick={done}>
                  C'est fait
                </button>
              </p>
            </>
          ) : (
            <>
              {st.logged_in ? (
                <InlineNotice kind="ok">Gemini est connecté à un compte Google : les meilleurs modèles sont utilisés.</InlineNotice>
              ) : (
                <InlineNotice kind="warn">
                  {st.logged_in === false
                    ? "Gemini n'est connecté à aucun compte : seuls des modèles limités sont utilisés."
                    : "Connexion à Gemini jamais vérifiée : conseillé de vous connecter à un compte Google."}
                </InlineNotice>
              )}
              {st.error && (
                <div style={{ marginTop: 10 }}>
                  <InlineNotice kind="bad">{st.error}</InlineNotice>
                </div>
              )}
              <p style={{ margin: "12px 0 0" }}>
                <button className={"button" + (st.logged_in ? "" : " button-primary")} onClick={open}>
                  {st.logged_in ? "Changer de compte Gemini" : "Se connecter à Gemini"}
                </button>
              </p>
            </>
          )}
        </div>
      </div>
    </>
  );
}

function Right({ ok, text }: { ok: boolean; text: string }) {
  return (
    <li className={ok ? "ok" : "bad"}>
      {ok ? <CheckCircle2 /> : <XCircle />}
      {text}
    </li>
  );
}
