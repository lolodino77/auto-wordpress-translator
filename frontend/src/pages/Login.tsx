import { useState, type FormEvent } from "react";
import { ArrowLeft, Eye, EyeOff, Languages } from "lucide-react";
import { api } from "../api";
import { errorText, useApp } from "../context";
import SetupGuide from "./SetupGuide";

/** Page de connexion, dans l'esprit de l'écran de connexion de WordPress (wp-login). */
export default function Login() {
  const { status, account, refreshAccount, refresh } = useApp();
  const [user, setUser] = useState("");
  const [pwd, setPwd] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const site = status?.site ?? "";
  // identifiants déjà enregistrés mais refusés ou site injoignable : on le dit dès l'arrivée
  const inherited = account?.configured && account.connected === false ? account.error : "";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.saveAccount(user, pwd);
      setPwd("");
      refreshAccount();
      refresh();
    } catch (err) {
      const msg = errorText(err);
      setError(typeof msg === "string" ? msg : "Connexion impossible.");
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-box">
        <div className="login-logo" aria-hidden>
          <Languages />
        </div>
        <h1 className="login-title">Traducteur d'articles</h1>

        {(error || inherited) && (
          <div className="login-error" role="alert">
            {error || inherited}
          </div>
        )}
        {!error && !inherited && (
          <p className="login-message">
            Ce programme prépare vos traductions en <strong>brouillons</strong> sur {site || "le site"}. Pour cela, il utilise un{" "}
            <strong>second compte WordPress, à part de votre compte habituel</strong>, qui a très peu de droits (le rôle{" "}
            <strong>« Contributeur »</strong>) : il peut seulement écrire des brouillons, jamais publier ni toucher aux articles des autres.
            Connectez-vous ci-dessous avec <strong>ce second compte</strong>.
          </p>
        )}

        <form className="login-form" onSubmit={submit} autoComplete="off">
          <label htmlFor="login-user">Identifiant WordPress</label>
          <input
            id="login-user"
            type="text"
            value={user}
            onChange={(e) => setUser(e.target.value)}
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            autoFocus
          />
          <label htmlFor="login-pass">Mot de passe d'application</label>
          <div className="login-pass">
            <input
              id="login-pass"
              type={show ? "text" : "password"}
              value={pwd}
              onChange={(e) => setPwd(e.target.value)}
              autoComplete="new-password"
              spellCheck={false}
            />
            <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Masquer le mot de passe" : "Afficher le mot de passe"}>
              {show ? <EyeOff /> : <Eye />}
            </button>
          </div>
          <div className="login-submit">
            <button type="submit" className="button button-primary" disabled={busy || !user.trim() || !pwd.trim()}>
              {busy ? "Vérification…" : "Se connecter"}
            </button>
          </div>
        </form>

        <SetupGuide site={site} />
      </div>
      {site && (
        <a className="login-back" href={/^https?:\/\//.test(site) ? site : `https://${site}`} target="_blank" rel="noreferrer">
          <ArrowLeft size={14} /> Aller sur {site}
        </a>
      )}
    </div>
  );
}
