import { useEffect, useState } from "react";
import { Languages } from "lucide-react";
import { api, type GeminiStatus, type LoginProvider } from "../api";
import { LOGIN_INFO } from "../util";
import { errorText, useApp } from "../context";

/** Écran proposé à chaque ouverture du programme (après la connexion WordPress) tant que Gemini (ou ChatGPT) n'est connecté
 *  à aucun compte. La connexion reste facultative (« Continuer sans compte »), mais l'utilisateur ne peut plus l'oublier
 *  et ne s'en aperçoit pas après le début d'une traduction. */
export default function LoginGate({ provider, onDone }: { provider: LoginProvider; onDone: () => void }) {
  const info = LOGIN_INFO[provider];
  const { notify } = useApp();
  const [st, setSt] = useState<GeminiStatus | null>(null);
  const [opened, setOpened] = useState(false); // la fenêtre de connexion a été ouverte depuis cet écran

  useEffect(() => {
    let alive = true;
    const load = (verify: boolean) =>
      api.llmLogin(provider, verify).then((s) => alive && setSt(s)).catch(() => undefined);
    load(true); // relit les cookies du profil : la connexion a pu expirer ou être faite en dehors du programme
    const t = window.setInterval(() => load(false), 2000); // suit la fenêtre de connexion
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [provider]);

  useEffect(() => {
    if (st?.window_open) setOpened(true);
  }, [st?.window_open]);

  // Déjà connecté (ou connexion réussie à la fermeture de la fenêtre) : on entre directement.
  useEffect(() => {
    if (st && st.logged_in && !st.window_open) onDone();
  }, [st, onDone]);

  async function open() {
    try {
      setSt(await api.llmLoginOpen(provider));
    } catch (e) {
      notify("error", errorText(e));
    }
  }

  async function done() {
    await api.llmLoginClose(provider).catch(() => undefined);
  }

  const failed = opened && st && !st.window_open && st.logged_in !== true;

  return (
    <div className="login-page">
      <div className="login-box">
        <div className="login-logo" aria-hidden>
          <Languages />
        </div>
        <h1 className="login-title">Compte {info.name}</h1>
        {st === null ? (
          <p className="login-message">Vérification…</p>
        ) : st.window_open ? (
          <>
            <p className="login-message">
              <strong>Une fenêtre Chrome est ouverte sur {info.name}.</strong> Cliquez sur « Se connecter » {info.where} et
              entrez votre {info.account}. Une fois connecté, fermez cette fenêtre Chrome (ou cliquez sur « C'est fait »).
            </p>
            <p className="login-message">
              {st.logged_in ? <strong style={{ color: "var(--green)" }}>✓ Connexion détectée.</strong> : "La connexion sera vérifiée à la fermeture de la fenêtre."}
            </p>
            <div className="login-submit">
              <button className="button button-primary" onClick={done}>
                C'est fait
              </button>
            </div>
          </>
        ) : (
          <>
            {(failed || st.error) && (
              <div className="login-error" role="alert">
                {st.error || `Aucune connexion à un ${info.account} n'a été détectée.`}
              </div>
            )}
            <p className="login-message">
              {info.name} n'est connecté à <strong>aucun {info.account}</strong>. {info.why} Connectez-vous maintenant (une seule
              fois, c'est gratuit) pour ne pas vous en apercevoir en pleine traduction. Le programme ne voit jamais votre mot de passe{" "}
              {info.password}.
            </p>
            <div className="login-submit" style={{ gap: 8 }}>
              <button className="button" onClick={onDone}>
                Continuer sans compte
              </button>
              <button className="button button-primary" onClick={open} autoFocus>
                Se connecter à {info.name}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
