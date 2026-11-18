import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

const FAQ: { q: string; a: ReactNode }[] = [
  {
    q: "Comment traduire un article ?",
    a: (
      <ol>
        <li>
          Ouvrez <Link to="/articles">Liste des articles à traduire</Link> : les articles en attente de traduction y sont listés.
        </li>
        <li>
          Cliquez sur <strong>Traduire et créer le brouillon</strong>. Vous suivez l'avancement dans le menu <Link to="/traduction">Traduction</Link>.
        </li>
        <li>
          À la fin, retrouvez votre brouillon dans <Link to="/resultats">Traductions faites</Link> : cliquez sur son titre pour l'ouvrir
          dans WordPress, relisez-le et finissez la mise en ligne vous-même.
        </li>
      </ol>
    ),
  },
  {
    q: "Le programme peut-il publier, modifier ou supprimer des articles sur le site ?",
    a: (
      <p>
        Non. Il utilise un compte au rôle <strong>Contributeur</strong> qui ne peut que créer des brouillons. La publication se fait toujours par
        vous, dans WordPress. Il ne touche jamais aux articles existants. Le menu <Link to="/reglages">Réglages</Link> affiche les droits exacts du
        compte.
      </p>
    ),
  },
  {
    q: "Combien de temps dure une traduction ?",
    a: (
      <p>
        Environ une minute par article (de 30 secondes à quelques minutes). Une fenêtre de navigateur s'ouvre : c'est elle qui dialogue avec l'outil de traduction (Gemini). Ne
        la fermez pas ; vous pouvez la réduire et continuer à travailler.
      </p>
    ),
  },
  {
    q: "Que dois-je vérifier avant de publier ?",
    a: (
      <p>
        Ouvrez le brouillon dans WordPress et relisez-le en entier. Pensez surtout à : compléter la légende de l'illustration (repère « À COMPLÉTER »),
        cocher « Enable Monarch Settings Override » en bas de l'éditeur, vérifier la catégorie et les étiquettes, et vérifier que les ouvrages cités
        n'ont pas déjà été traduits en français.
      </p>
    ),
  },
  {
    q: "Un article est marqué « Erreur » : que faire ?",
    a: (
      <>
        <p>
          Le message d'erreur s'affiche sous le titre, dans la liste. Le plus souvent : outil de traduction saturé, site anglais inaccessible ou
          notes de bas de page incohérentes (la traduction est alors refusée par sécurité).
        </p>
        <p>
          Réessayez avec <strong>Traduire</strong> (survolez le titre). Si le site anglais bloque la lecture (article réservé aux abonnés…), copiez le
          texte dans un fichier .md et ajoutez-le par l'onglet « Par fichier .md ».
        </p>
      </>
    ),
  },
  {
    q: "J'ai retraduit un article : il y a maintenant deux brouillons",
    a: <p>C'est normal : l'ancien brouillon n'est jamais supprimé automatiquement. Mettez-le à la corbeille vous-même dans WordPress.</p>,
  },
  {
    q: "L'outil de traduction affiche un message ou demande de se connecter",
    a: (
      <p>
        La fenêtre ouverte pendant la traduction est un vrai navigateur : vous pouvez y fermer un message. Si Gemini est indisponible, ChatGPT prend
        le relais automatiquement (ordre réglable dans <Link to="/reglages">Réglages</Link>).
      </p>
    ),
  },
  {
    q: "Où sont rangés les fichiers ?",
    a: (
      <ul>
        <li>
          <code>input/articles.csv</code> : la liste des adresses à traduire.
        </li>
        <li>
          <code>input/articles_md/</code> : les fichiers .md ajoutés.
        </li>
        <li>
          <code>input/corbeille/</code> : les fichiers .md retirés de la liste (récupérables).
        </li>
        <li>
          <code>output/</code> : les traductions et les fiches de relecture.
        </li>
      </ul>
    ),
  },
  {
    q: "Comment fermer ou relancer le programme ?",
    a: (
      <p>
        Pour l'arrêter, fermez la fenêtre noire ouverte au lancement. Pour le relancer, double-cliquez sur « Lancer le traducteur » : cette page
        s'ouvre toute seule. Attendez la fin d'une traduction en cours avant de fermer. Après une mise à jour, inutile de relancer : le
        programme redémarre tout seul (jamais pendant une traduction) et cette page se met à jour d'elle-même.
      </p>
    ),
  },
];

export default function Help() {
  return (
    <>
      <h1 className="page-title">Aide</h1>
      <p className="page-intro">Les réponses aux questions les plus courantes. Cliquez sur une question pour afficher la réponse.</p>
      <div className="faq">
        {FAQ.map((f, i) => (
          <details key={f.q} open={i === 0}>
            <summary>
              <ChevronRight />
              {f.q}
            </summary>
            <div className="answer">{f.a}</div>
          </details>
        ))}
      </div>
    </>
  );
}
