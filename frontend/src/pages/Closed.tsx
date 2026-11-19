import { Languages, Power } from "lucide-react";

/** Écran affiché après « Quitter » : le programme est arrêté, la page ne peut plus rien faire. */
export default function Closed() {
  return (
    <div className="login-page">
      <div className="login-box">
        <div className="login-logo" aria-hidden>
          <Languages />
        </div>
        <h1 className="login-title">Le Traducteur est fermé</h1>
        <p className="login-message">
          <Power size={14} style={{ verticalAlign: "-2px" }} /> Le programme est arrêté. Vous pouvez fermer cet onglet.
          <br />
          Pour le rouvrir, double-cliquez sur <strong>« Ouvrir le Traducteur »</strong> (ou sur l'icône « Traducteur d'articles ») dans le dossier du Traducteur.
        </p>
      </div>
    </div>
  );
}
