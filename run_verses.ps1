# Relance la pipeline complète (extraction -> traduction -> règles -> brouillon WP) pour les articles du CSV qui contiennent
# des versets bibliques : lignes 1, 2 et 5 de input/articles.csv (repérées par find_verses.py).
$py = "C:\Users\cvthb\anaconda3\envs\auto-wordpress-translator\python.exe"
foreach ($n in 1, 2, 5) {
    Write-Host "===== Article $n ====="
    & $py agent.py --only $n
}
