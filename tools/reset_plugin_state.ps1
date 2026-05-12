# プラグインを物理削除 (./plugins/<name>/ を rm) した後、Redmine が
# boot ループする場合の脱出ハッチ。
#
# DB の plugin_schema_migrations から該当プラグインの migration 履歴を
# 消すことで、Redmine 起動時の整合性チェックを通す。
#
# 注:
#   - プラグインが作ったテーブルそのものは残る (=データはそのまま)。
#     不要なら手動で DROP TABLE してください。
#   - これでも復旧しない場合は docs/plugin_install.md の
#     「最終手段: 完全リセット」セクション参照。
#
# 使い方:
#   .\tools\reset_plugin_state.ps1 redmine_some_plugin
#
# 詳細: docs/plugin_install.md

param([Parameter(Mandatory=$true)][string]$PluginName)

# 注: PS 5.1 で native の stderr を error 扱いさせないため EAP=Continue。
$ErrorActionPreference = 'Continue'

# .env から MySQL の認証情報を取り出す (簡易)
function Get-EnvOrDefault([string]$key, [string]$fallback) {
    $envPath = Join-Path (Split-Path $PSScriptRoot -Parent) '.env'
    if (Test-Path $envPath) {
        $line = Get-Content $envPath | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
        if ($line) { return ($line -split '=', 2)[1] }
    }
    return $fallback
}

$db   = Get-EnvOrDefault 'MYSQL_DATABASE' 'redmine'
$user = Get-EnvOrDefault 'MYSQL_USER'     'redmine'
$pass = Get-EnvOrDefault 'MYSQL_PASSWORD' 'redmine_pw'

Write-Host "DB '$db'.plugin_schema_migrations から plugin_name LIKE '$PluginName' を削除..."
docker compose exec -T db mysql -u $user "-p$pass" $db `
    -e "DELETE FROM plugin_schema_migrations WHERE plugin_name LIKE '$PluginName';"
Write-Host ""
Write-Host "tmp:clear (失敗しても継続)..."
docker compose exec -T redmine bundle exec rake tmp:clear RAILS_ENV=production# 起動失敗中はここで失敗する可能性があるが、続行する

Write-Host ""
Write-Host "restart redmine..."
docker compose restart redmine
Start-Sleep -Seconds 3
Write-Host ""
Write-Host "--- 直近ログ ---"
docker compose logs --tail 30 redmine