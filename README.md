# auto-wordpress-translator
Projet d'IA agentique pour traduire et générer automatiquement des traductions d'articles sur WordPress

Pour chaque article à traduire (une URL, ou un fichier `.md`), l'agent : récupère le texte, le fait traduire de l'anglais
vers le français par Gemini (ou ChatGPT en secours) dans un navigateur, applique les règles éditoriales de la revue
(dossier `spec/`), puis crée un **brouillon** sur WordPress. Il ne publie **jamais** : un brouillon est relu et publié
à la main.

## Sommaire
1. [Installation](#1-installation)
2. [Configuration](#2-configuration)
3. [Utilisation](#3-utilisation)
4. [Ce que fait la pipeline](#4-ce-que-fait-la-pipeline)
5. [Fichiers produits](#5-fichiers-produits)
6. [Droits du compte WordPress](#6-droits-du-compte-wordpress)
7. [Tests](#7-tests)
8. [Limites connues](#8-limites-connues)
9. [Plan du projet](#9-plan-du-projet)

## 1. Installation

Prérequis : Anaconda (ou Miniconda) sous Windows, et un navigateur.

```bash
powershell -ExecutionPolicy Bypass -File setup_env.ps1
conda activate auto-wordpress-translator
```

`setup_env.ps1` crée l'environnement conda `auto-wordpress-translator` à partir de `environment.yml` (Python 3.12 ;
trafilatura, playwright, requests, truststore, pypdf) et télécharge le navigateur Chromium de Playwright.

Si Gemini ou ChatGPT demandent une connexion, `python agent.py --login` ouvre les deux sites : connectez-vous à la main
dans la fenêtre. Gemini a répondu sans connexion lors de nos essais ; ChatGPT, de façon moins fiable.

## 2. Configuration

Tout se règle dans `config.toml` :

| Réglage | Rôle |
|---|---|
| `[wordpress] mode` | `"selfhosted"` pour un WordPress auto-hébergé (ex. parlafoi.fr), `"wpcom"` pour un site WordPress.com |
| `[wordpress] site` | adresse du site |
| `[wordpress] scope` | mode `wpcom` seulement : droits demandés à WordPress.com (`"posts taxonomy"`) |
| `[specs] dir` | dossier des PDF de règles éditoriales (`spec/`), lus et injectés dans le prompt à chaque exécution |
| `[llm] engines` | ordre des moteurs : `["gemini", "gpt"]` (le suivant sert de secours) |
| `[llm] max_words` | au-delà, l'article est refusé (à découper à la main) |
| `[llm] prompt` | consigne envoyée au LLM |

Autres fichiers de réglage : `bible_abbreviations.toml` (abréviations des livres bibliques, voir [§4](#4-ce-que-fait-la-pipeline)).

### Identifiants WordPress (une seule fois, en saisie masquée dans le terminal)

```bash
python agent.py --auth
```

- **Site auto-hébergé** (`mode = "selfhosted"`) : le programme demande le **nom d'utilisateur** et un **mot de passe d'application**
  (créé dans l'administration du site : Utilisateurs, Profil, « Mots de passe d'application »). Il vérifie les identifiants,
  affiche le compte et son rôle, et les enregistre dans `wp_credentials.json`.
- **Site WordPress.com** (`mode = "wpcom"`) : il faut d'abord créer une application sur developer.wordpress.com
  (URL de redirection `http://localhost:8765/callback`), puis `--auth` demande son Client ID et son secret et ouvre
  l'écran d'autorisation. Le jeton est enregistré dans `wp_token.json`. Connectez-vous avec le **bon compte** avant de cliquer
  sur « Connect » : l'application a les droits de ce compte.

Ne partagez jamais `wp_credentials.json` ni `wp_token.json` (ils sont exclus de Git).

## 3. Utilisation

### Entrées possibles

**Un CSV** (`input/articles.csv`) : une URL par ligne, étiquettes éventuelles en 2e colonne séparées par `;`. L'en-tête
`url,tags` est facultatif.

```
https://www.logos.com/grow/min-what-jeremiah-2911-means/,
https://exemple.org/article,foi;Bible
```

**Un dossier de fichiers markdown** (`input/articles_md/`) : un `.md` par article. Le titre est le nom du fichier ; les images
et l'en-tête d'un export Substack (auteur, date, likes) sont retirés ; l'URL d'origine est retrouvée quand c'est possible.

### Commandes

```bash
conda activate auto-wordpress-translator
python agent.py                       # traite les URLs de input/articles.csv (celles déjà faites sont sautées)
python agent.py --only 3              # un seul élément (1 = premier), même s'il est déjà fait
python agent.py --force               # retraite tout, même ce qui est déjà fait (crée de nouveaux brouillons)
python agent.py --md                  # traite tous les .md de input/articles_md/ et crée les brouillons
python agent.py --md --only 1         # un seul fichier (1 = premier par ordre alphabétique)
python agent.py --md AUTRE\DOSSIER    # un autre dossier
python agent.py --csv autre.csv       # un autre CSV
python dry_run.py --md --engine gemini   # aperçu local, sans rien publier
```

`dry_run.py` fait tout sauf la création du brouillon : il écrit seulement dans `output/`. Il accepte aussi `--csv`, `--md` et `--only`.

Pendant une exécution, une fenêtre de navigateur s'ouvre : laissez-la ouverte, sans cliquer dedans. Comptez environ 30 à 90 secondes
par article avec Gemini. À la fin, le terminal liste chaque article avec « brouillon créé » ou « erreur ». Les articles en erreur sont
retraités à la relance suivante.

## 4. Ce que fait la pipeline

```
URL du CSV ──► extract.py ─┐
                           ├─► pipeline.py ─► llm_browser.py ─► rules.py ─► wp_selfhosted.py / wp.py ─► brouillon
fichier .md ─► extract.py ─┘       │                (Gemini/ChatGPT)    (règles)       (création, status=draft)
                                   └─ specs.py : lit spec/*.pdf et les ajoute au prompt
```

1. **Chargement** (`extract.py`, `inputs.py`) : une page web est téléchargée (secours par navigateur si le téléchargement
   simple échoue) et réduite à son texte. Les notes de bas de page sont retrouvées et marquées `[NOTE n]` ; les listes
   « articles liés » sont retirées ; le suffixe « - Nom du site » est enlevé du titre.
2. **Prompt** (`pipeline.py`, `specs.py`) : l'article, le texte des PDF de `spec/` et les consignes sont envoyés au LLM.
3. **Traduction** (`llm_browser.py`) : Gemini, puis ChatGPT en secours. La réponse (titre, étiquettes, identifiant, HTML) est
   relue ; une réponse non traduite ou mal formée est refusée et le moteur suivant est essayé.
4. **Règles éditoriales** (`rules.py`), appliquées de façon déterministe : titres en H3/H4, `XX<sup>e</sup>`, guillemets « »
   avec espaces insécables, références bibliques « Livre Chapitre,Verset » (noms complets, abréviations de la Bible de Jérusalem
   en note ou en liste, fichier `bible_abbreviations.toml`), notes de bas de page en `[[…]]`, introduction du traducteur en italique
   suivie d'un séparateur, séparateur final s'il y a des notes, balises HTML non prévues retirées, URL nues transformées en liens.
5. **Identifiant (slug)** : titre raccourci aux noms et mots importants (ex. `projets-dieu-jeremie-2911`), vérifié par rapport au titre.
6. **Garde-fou sur les notes** : une traduction dont le nombre de notes ne correspond pas à la source (notes inventées, perdues,
   mal fermées) n'est **jamais publiée** (2 essais par moteur) ; le texte refusé est gardé dans `output/rejected/`.
7. **Brouillon** : création avec `status=draft` uniquement. Le code n'envoie ni publication, ni modification, ni suppression.
8. **Fiche de relecture** : `output/review/<article>.md` liste ce qui a été corrigé, les doutes, et les actions manuelles.

## 5. Fichiers produits

| Fichier ou dossier | Contenu |
|---|---|
| `output/review/*.md` | une fiche de relecture par article |
| `output/rejected/` | traductions refusées par le garde-fou, pour inspection |
| `output/NN-*.html`, `output/NN-*.source.md` | aperçu et texte source (`dry_run.py` seulement) |
| `agent.log` | journal détaillé |
| `state-<site>.db` | base d'état **par site** : ce qui a déjà été traité (supprimez-la ou utilisez `--force` pour tout refaire) |
| `browser_profile/` | profil du navigateur automatisé |
| `wp_credentials.json`, `wp_token.json` | identifiants WordPress (à ne pas partager) |

## 6. Droits du compte WordPress

Pour que l'application ne puisse **jamais publier**, utilisez pour elle un compte dédié avec le rôle **Contributeur** : il peut créer et
modifier ses propres articles, mais ni les publier, ni toucher à ceux des autres. Cette limite est appliquée par WordPress lui-même, pas
seulement par le code.

Le dossier `checks/` contient des essais à lancer à la main pour le vérifier (voir `checks/README.md`) :

```bash
python checks/whoami.py                        # compte, rôle et droits (lecture seule)
python checks/selfhosted/check_permissions.py  # tente de modifier/supprimer l'article d'un autre, de publier un test
python checks/selfhosted/preflight.py          # avant une exécution : compte, catégories, étiquettes, CSV (lecture seule)
python checks/selfhosted/check_draft.py ID     # relit un brouillon créé (lecture seule)
```

Pour un site WordPress.com, les équivalents sont dans `checks/wpcom/`.

## 7. Tests

```bash
python -m unittest test_rules
```

Environ 100 tests vérifient le code avec un faux réseau (règles, notes, slug, CSV, fichiers `.md`, module WordPress). Ils ne contactent
jamais WordPress ni les LLM et ne prouvent donc rien sur les droits réels du compte : pour cela, utilisez `checks/`.

## 8. Limites connues

- **Catégories et étiquettes** : sur `parlafoi.fr`, le plugin Kadence Security refuse au compte la lecture des catégories et des étiquettes
  (`itsec_rest_api_access_restricted`). Les brouillons sont créés sans elles ; elles figurent dans la fiche de relecture, à ajouter à la main.
  Un compte Contributeur ne peut de toute façon pas créer de nouvelles étiquettes.
- **Étapes manuelles de la spec** : case « Enable Monarch Settings Override », choix d'une illustration libre de droits et de sa
  légende, vérification qu'un ouvrage cité n'a pas déjà été traduit en français.
- **Les LLM se trompent** : Gemini invente parfois des détails (un éditeur, une année, une note), un intertitre ou un identifiant erroné.
  Le garde-fou et les contrôles en attrapent une partie, pas tout : **relisez chaque brouillon**.
- **Règles de langue non vérifiées par le code** : église/Église, Évangile/évangile, mots étrangers en italique, format des références
  bibliographiques (Lausanne) ; elles sont seulement demandées au LLM.
- **Images** : l'agent n'en envoie pas ; celles d'un fichier `.md` sont retirées.
- **Abréviations bibliques** : celles de la Bible de Jérusalem (tableau de Lacroux, *Orthotypographie*), faute de norme officielle unique.
  Modifiables dans `bible_abbreviations.toml`.
- **Pas de lancement automatique** : l'agent se lance à la main (le PC doit rester allumé, la fenêtre du navigateur visible).
- **ChatGPT** n'a pas répondu de façon fiable en secours : Gemini est le moteur validé.

## 9. Plan du projet

| Fichier | Rôle |
|---|---|
| `agent.py` | point d'entrée : identifiants, boucle sur les articles, état, journal |
| `inputs.py` | liste des travaux (CSV ou dossier `.md`) |
| `extract.py` | lecture d'une page web ou d'un `.md`, notes de bas de page, nettoyage |
| `specs.py` | lecture des PDF de `spec/` |
| `pipeline.py` | prompt, traduction avec garde-fou, fiche de relecture |
| `llm_browser.py` | pilotage de Gemini / ChatGPT (Playwright) et lecture de la réponse |
| `rules.py` | règles éditoriales et slug |
| `bible.py`, `bible_abbreviations.toml` | livres et abréviations bibliques |
| `wp_selfhosted.py` | brouillons sur un WordPress auto-hébergé (API `wp-json`, mot de passe d'application) |
| `wp.py` | brouillons sur WordPress.com (OAuth) |
| `dry_run.py` | essai local sans création de brouillon |
| `checks/` | contrôles des droits du compte (à lancer à la main) |
| `test_rules.py` | tests automatiques |
| `spec/` | règles éditoriales de la revue (PDF) |
| `input/` | CSV et fichiers `.md` à traduire |

Quelques scripts à la racine sont des outils d'essai ou de diagnostic (`check_drafts.py`, `check_refs.py`, `show_notes.py`,
`find_verses.py`, `test_extract.py`, `test_llm.py`, `inspect_gpt.py`, `draft_test.py`, `run_*.ps1`). Ils ne font pas partie de la pipeline.
