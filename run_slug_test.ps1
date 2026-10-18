# Essai réel de l'identifiant (slug) : relance l'article 1 puis relit le brouillon créé.
$py = "C:\Users\cvthb\anaconda3\envs\auto-wordpress-translator\python.exe"
& $py agent.py --only 1
$line = Select-String -Path agent.log -Pattern "OK .*logos" | Select-Object -Last 1
$id = [regex]::Match($line.Line, "p=(\d+)").Groups[1].Value
Write-Host "Brouillon créé : $id"
& $py check_drafts.py $id
