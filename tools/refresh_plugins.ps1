# プラグインを ./plugins/ に出し入れした後、変更を Redmine に反映する。
# 実行内容:
#   1. redmine:plugins:migrate (各プラグインの DB マイグレーション)
#   2. tmp:clear              (起動時キャッシュをクリア)
#   3. docker compose restart redmine
#
# どれもエラーが起きる可能性があるので、失敗したら下記の脱出ハッチを使う:
#   .\tools\reset_plugin_state.ps1 <plugin_name>
#
# 詳細: docs/plugin_install.md

# 注: PS 5.1 + EAP=Stop だと native コマンドの stderr で止まるため EAP=Continue。
# 各ステップで $LASTEXITCODE を見て失敗を集計する。
$ErrorActionPreference = 'Continue'
$failed = 0

Write-Host "[1/3] plugins:migrate..."
docker compose exec -T redmine bundle exec rake redmine:plugins:migrate RAILS_ENV=production
if ($LASTEXITCODE -ne 0) { $failed++; Write-Host "  → plugins:migrate failed" -ForegroundColor Red }

Write-Host ""
Write-Host "[2/3] tmp:clear..."
docker compose exec -T redmine bundle exec rake tmp:clear RAILS_ENV=production
if ($LASTEXITCODE -ne 0) { $failed++; Write-Host "  → tmp:clear failed" -ForegroundColor Red }

Write-Host ""
Write-Host "[3/3] restart redmine..."
docker compose restart redmine
if ($LASTEXITCODE -ne 0) { $failed++; Write-Host "  → restart failed" -ForegroundColor Red }

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "--- 直近ログ ---"
docker compose logs --tail 20 redmine
if ($failed -gt 0) {
    Write-Host ""
    Write-Host "$failed 個のステップが失敗。失敗時は ./tools/reset_plugin_state.ps1 <name> を検討してください。" -ForegroundColor Red
    exit 1
}
