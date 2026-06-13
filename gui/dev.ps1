# Mata qualquer processo na porta 17432 antes de iniciar
$pid17432 = (netstat -ano | findstr :17432 | ForEach-Object { ($_ -split '\s+')[-1] } | Select-Object -First 1)
if ($pid17432) {
    Write-Host "Matando processo $pid17432 na porta 17432..."
    taskkill /PID $pid17432 /F
    Start-Sleep -Seconds 1
}
npm run tauri:dev