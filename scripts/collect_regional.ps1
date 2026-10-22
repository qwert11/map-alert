# История областных и доп. общенациональных каналов с 2024 -> _tmp/hist_reg/ (для траекторий)
Set-Location (Split-Path $PSScriptRoot)
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Force '_tmp\hist_reg' | Out-Null
$jobs = @(
  @('vinnytsia_golovne', 29000, 0), @('vinnitsa_info', 56800, 28000), @('vinnitsa_info', 28000, 0),
  @('khmelnych', 16700, 0), @('khmlv', 39900, 20000), @('khmlv', 20000, 0), @('zt_radar', 5300, 0),
  @('rivne_golovne', 60500, 30000), @('rivne_golovne', 30000, 0), @('rivne_radar', 33100, 0),
  @('truexaternopil', 31600, 0), @('lviv_golovne', 45100, 0), @('truexafrankivsk', 38400, 0),
  @('Lutsk_monitor', 1600, 0), @('lutsk_radar', 2500, 0), @('cherkasy_golovne', 21400, 0), @('cherkasy_radar', 6300, 0),
  @('kyivradar', 83800, 56000), @('kyivradar', 56000, 28000), @('kyivradar', 28000, 0),
  @('kudy_letyt', 126500, 95000), @('kudy_letyt', 95000, 65000), @('kudy_letyt', 65000, 0),
  @('deraketaua', 66200, 33000), @('deraketaua', 33000, 0)
)
foreach ($j in $jobs) {
  $out = "_tmp\hist_reg\$($j[0])_$($j[1]).jsonl"
  $log = "_tmp\hist_reg\$($j[0])_$($j[1]).log"
  Start-Process python -ArgumentList 'scripts\collect_range.py', $j[0], $j[1], $j[2], $out, '2024-01-01' `
    -RedirectStandardOutput $log -RedirectStandardError "$log.err" -WindowStyle Hidden
  Start-Sleep -Milliseconds 700
}
