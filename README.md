# auto-wordpress-translator
Projet d'IA agentique pour traduire et générer automatiquement des traductions d'articles sur WordPress


conda activate auto-wordpress-translator
python agent.py --md                  # traite tous les .md de input/articles_md/ et crée les brouillons
python agent.py --md --only 1         # un seul fichier (1 = premier par ordre alphabétique)
python agent.py --md AUTRE\DOSSIER    # un autre dossier
python dry_run.py --md --engine gemini   # aperçu local, sans rien publier