import { useState, type ReactNode } from "react";
import { Check, Copy, ShieldCheck, UserCog, UserRound } from "lucide-react";

type Role = "admin" | "editor";

/** Capture d'écran d'une étape (fichier dans frontend/public/aide/). Masquée tant que le fichier n'existe pas. */
function Shot({ file, alt }: { file: string; alt: string }) {
  const [ok, setOk] = useState(true);
  if (!ok) return null;
  return (
    <figure className="guide-shot">
      <img src={`/aide/${file}`} alt={alt} loading="lazy" onError={() => setOk(false)} />
    </figure>
  );
}

function Step({ n, title, children }: { n: number; title: string; children?: ReactNode }) {
  return (
    <li className="guide-step">
      <span className="guide-num">{n}</span>
      <div>
        <h3>{title}</h3>
        {children}
      </div>
    </li>
  );
}

/** Choix « administrateur / éditeur » et procédure pas à pas pour obtenir un mot de passe d'application. */
export default function SetupGuide({ site }: { site: string }) {
  const [role, setRole] = useState<Role | null>(null);
  const [copied, setCopied] = useState(false);
  const host = site || "le site";
  const message =
    `Bonjour,\n\nPour utiliser le Traducteur d'articles, j'ai besoin d'un second compte WordPress sur ${host}, ` +
    `distinct de mon compte principal :\n- rôle : Contributeur (pas Éditeur) ;\n- une adresse e-mail différente de la mienne ` +
    `(par exemple mon.adresse+traduction@gmail.com).\n\nCe compte ne pourra que créer et gérer ses propres brouillons, jamais publier. ` +
    `Merci !`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(message);
    } catch {
      /* copie impossible : le texte reste sélectionnable */
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  const needSecondAccount = (
    <div className="inline-notice warn">
      <UserCog />
      <div>
        <strong>Vous avez besoin d'un second compte, avec beaucoup moins de droits que votre compte principal.</strong> Ce compte doit avoir
        le rôle <strong>Contributeur</strong> : il peut seulement créer, gérer et supprimer <em>ses propres brouillons</em>, jamais publier.{" "}
        {role === "editor" ? (
          <>
            Votre compte d'éditeur n'a pas le droit d'en créer un : <strong>demandez-le à un administrateur</strong>.
          </>
        ) : (
          <>Si ce compte n'existe pas encore, créez-le à l'étape 1.</>
        )}
      </div>
    </div>
  );

  return (
    <div className="guide">
      <p className="guide-ask">Pas encore de mot de passe d'application ? Qui êtes-vous ?</p>
      <div className="guide-choice" role="group" aria-label="Votre rôle sur le site">
        <button type="button" className={role === "admin" ? "on" : ""} aria-pressed={role === "admin"} onClick={() => setRole("admin")}>
          <ShieldCheck /> Je suis administrateur
        </button>
        <button type="button" className={role === "editor" ? "on" : ""} aria-pressed={role === "editor"} onClick={() => setRole("editor")}>
          <UserRound /> Je suis éditeur
        </button>
      </div>

      {role === "editor" && (
        <div className="guide-body">
          {needSecondAccount}
          <h3 className="guide-sub">Étape 0 : demandez ce compte à un administrateur</h3>
          <p>Copiez ce message et envoyez-le à un administrateur du site :</p>
          <pre className="guide-message">{message}</pre>
          <button type="button" className="button" onClick={copy}>
            {copied ? <Check /> : <Copy />} {copied ? "Copié !" : "Copier le message"}
          </button>
          <p className="guide-then">
            Quand l'administrateur vous confirme que le compte est créé, suivez les étapes ci-dessous <strong>avec ce nouveau compte</strong> :
          </p>
          <AppPasswordSteps host={host} first={1} role="editor" />
        </div>
      )}

      {role === "admin" && (
        <div className="guide-body">
          {needSecondAccount}
          <ol className="guide-steps">
            <Step n={1} title="Créez le compte limité (une seule fois)">
              <p>
                Connectez-vous à <strong>{host}/wp-admin</strong>. Dans le menu de gauche, cliquez sur <strong>Comptes</strong> puis{" "}
                <strong>Ajouter un compte</strong>. Choisissez un identifiant (par exemple « traduction »), une adresse e-mail <strong>différente</strong>{" "}
                de celles des autres comptes, et le rôle <strong>Contributeur</strong>. Cliquez sur <strong>Ajouter un compte</strong>.
              </p>
              <Shot file="a1-ajouter-compte.png" alt="Formulaire d'ajout d'un compte, rôle Contributeur" />
            </Step>
          </ol>
          <AppPasswordSteps host={host} first={2} role="admin" />
        </div>
      )}
    </div>
  );
}

function AppPasswordSteps({ host, first, role }: { host: string; first: number; role: Role }) {
  const admin = role === "admin";
  const n = admin ? first : first + 1; // numéro de l'étape « ouvrir le compte »
  return (
    <ol className="guide-steps">
      {!admin && (
        <Step n={first} title="Connectez-vous avec le compte limité">
          <p>
            Ouvrez <strong>{host}/wp-admin</strong> et connectez-vous avec <strong>le compte Contributeur</strong> (pas votre compte
            principal). Astuce : utilisez une fenêtre de navigation privée pour ne pas être déconnecté de votre compte habituel.
          </p>
        </Step>
      )}
      {admin ? (
        <Step n={n} title="Ouvrez le compte limité">
          <p>
            Connecté à <strong>{host}/wp-admin</strong>, cliquez dans le menu noir à gauche sur <strong>Comptes</strong>, puis sur le compte
            limité (par exemple « autotraduction ») pour le modifier. Descendez tout en bas de la page, jusqu'à la zone{" "}
            <strong>« Mots de passe d'application »</strong>.
          </p>
          <Shot file="1-comptes.png" alt="Menu Comptes de WordPress" />
        </Step>
      ) : (
        <Step n={n} title="Ouvrez votre Profil">
          <p>
            Avec ce compte limité, le menu noir à gauche s'appelle <strong>Profil</strong> : cliquez dessus, puis descendez tout en bas de
            la page, jusqu'à la zone <strong>« Mots de passe d'application »</strong>.
          </p>
          <Shot file="1-profil.png" alt="Menu Profil de WordPress" />
        </Step>
      )}
      <Step n={n + 1} title="Créez le mot de passe">
        <p>
          Dans la case « Nouveau nom du mot de passe d'application », écrivez par exemple <strong>Traducteur</strong>, puis cliquez sur le
          bouton <strong>Ajouter un mot de passe d'application</strong>.
        </p>
        <Shot file="2-nouveau-mot-de-passe.png" alt="Zone Mots de passe d'application" />
      </Step>
      <Step n={n + 2} title="Copiez-le et collez-le ci-dessus">
        <p>
          WordPress affiche un mot de passe de plusieurs groupes de lettres.{" "}
          <strong>Copiez-le tout de suite : il ne sera plus jamais affiché.</strong> Collez-le dans le champ « Mot de passe d'application » de
          cette page, avec l'identifiant du compte limité, puis cliquez sur <strong>Se connecter</strong>.
        </p>
        <Shot file="3-mot-de-passe-affiche.png" alt="Mot de passe d'application affiché par WordPress" />
        <p className="guide-note">
          Ce n'est pas le mot de passe habituel du compte : il ne sert qu'à ce programme et peut être supprimé à tout moment depuis le même
          écran.
        </p>
      </Step>
    </ol>
  );
}
