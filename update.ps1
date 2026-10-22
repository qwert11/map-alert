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
# свежие посты областных каналов — только для траекторий (build_paths.py); история с 2024 — scripts\collect_regional.ps1
foreach ($c in 'kudy_letyt', 'deraketaua', 'vinnytsia_golovne', 'vinnitsa_info', 'khmelnych', 'khmlv', 'zt_radar',
               'rivne_golovne', 'rivne_radar', 'truexaternopil', 'lviv_golovne', 'truexafrankivsk', 'Lutsk_monitor',
               'lutsk_radar', 'cherkasy_golovne', 'cherkasy_radar', 'kyivradar') {
  python scripts\collect_tg.py $c $Since 2>&1 | Select-Object -Last 1 | ForEach-Object { Log $_ }
}
python scripts\split_nights.py 2>&1 | Out-File -Append -Encoding utf8 $log
python scripts\run_extract.py $Parallel 2>&1 | Select-Object -Last 1 | ForEach-Object { Log $_ }
python scripts\build_alerts.py $Since 2>&1 | ForEach-Object { Log $_ }
python scripts\build_site.py 2>&1 | ForEach-Object { Log $_ }
python scripts\build_strikes.py 2>&1 | ForEach-Object { Log $_ }
python scripts\build_flights.py 2>&1 | Select-Object -First 3 | ForEach-Object { Log $_ }
python scripts\build_paths.py --reparse 2>&1 | Select-Object -Last 6 | ForEach-Object { Log $_ }

git add data index.html app.js style.css scripts README.md update.ps1 .gitignore
git commit -q -m "Данные: обновление $(Get-Date -Format 'yyyy-MM-dd HH:mm')" 2>&1 | Out-Null
git push -q 2>&1 | ForEach-Object { Log $_ }
Log 'ALLDONE'
