# Полное обновление карты: посты каналов -> ночи -> извлечение (claude -p) -> данные сайта -> push.
# Запускать отдельным процессом (долго):
#   Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','update.ps1' -WindowStyle Hidden
# Лог: _tmp\update.log
param([string]$Since = '2026-09-20', [int]$Parallel = 5)
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$log = Join-Path $PSScriptRoot '_tmp\update.log'
New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot '_tmp') | Out-Null
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" | Out-File -Append -Encoding utf8 $log }

Log "start since=$Since"
foreach ($c in 'kpszsu', 'monitorwarr', 'war_monitor', 'vanek_nikolaev') {
  python scripts\collect_tg.py $c $Since 2>&1 | Select-Object -Last 1 | ForEach-Object { Log $_ }
}
python scripts\split_nights.py 2>&1 | Out-File -Append -Encoding utf8 $log
python scripts\run_extract.py $Parallel 2>&1 | Select-Object -Last 1 | ForEach-Object { Log $_ }
python scripts\build_alerts.py $Since 2>&1 | ForEach-Object { Log $_ }
python scripts\build_site.py 2>&1 | ForEach-Object { Log $_ }
python scripts\build_strikes.py 2>&1 | ForEach-Object { Log $_ }

git add data index.html app.js style.css scripts README.md update.ps1 .gitignore
git commit -q -m "Данные: обновление $(Get-Date -Format 'yyyy-MM-dd HH:mm')" 2>&1 | Out-Null
git push -q 2>&1 | ForEach-Object { Log $_ }
Log 'ALLDONE'
