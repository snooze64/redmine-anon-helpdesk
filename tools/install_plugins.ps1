# 推奨プラグインを ./plugins/ に取得する (clone または git pull で更新)。
#
# このプロジェクトでは Redmine プラグインを Dockerfile に焼き込まず、ホストの
# ./plugins/ を bind-mount で読み込んでいるので、git clone するだけで増やせる。
#
# 推奨プラグイン (= 本リポジトリの想定構成で使うもの) は下の $plugins 配列に
# 列挙してある。手元で追加のプラグインを試したい場合は、このスクリプトに
# 行を足すか、`cd plugins && git clone <URL>` で直接置いてもよい。
#
# 取得後の反映: docker compose up 後に ./tools/refresh_plugins.ps1 を実行。
#
# 詳細: docs/plugin_install.md

# 注: PowerShell 5.1 (Windows 標準) は native コマンドの stderr を ErrorRecord
# として扱い、ErrorActionPreference=Stop と組み合わせると git の通常出力
# (Cloning into ... 等) でも止まる。EAP は既定の Continue のままにして、
# $LASTEXITCODE で明示チェックする。
$ErrorActionPreference = 'Continue'

# (name, repo url) の組。pin したい場合は git -C plugins/<name> checkout <tag> を別途。
$plugins = @(
  @{ name = 'redmine_hidden_user_profile'; url = 'https://github.com/JGallot/redmine_hidden_user_profile.git' },
  @{ name = 'view_customize';              url = 'https://github.com/onozaty/redmine-view-customize.git'      },
  @{ name = 'redmine_ai_helper';           url = 'https://github.com/haru/redmine_ai_helper.git'             }
)

$root       = Split-Path $PSScriptRoot -Parent
$pluginsDir = Join-Path $root 'plugins'
if (-not (Test-Path $pluginsDir)) { New-Item -ItemType Directory -Path $pluginsDir | Out-Null }

$failed = @()
foreach ($p in $plugins) {
    $dst = Join-Path $pluginsDir $p.name
    if (Test-Path (Join-Path $dst '.git')) {
        $safeDst = (Resolve-Path -LiteralPath $dst).ProviderPath -replace '\\', '/'
        Write-Host "[$($p.name)] git pull..."
        git -c "safe.directory=$safeDst" -C $dst pull --ff-only
    } else {
        Write-Host "[$($p.name)] git clone..."
        git clone --depth 1 $p.url $dst
    }
    if ($LASTEXITCODE -ne 0) { $failed += $p.name }
}

if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "失敗したプラグイン: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "完了。次に以下を実行してください:"
Write-Host "  docker compose up -d"
Write-Host "  .\tools\refresh_plugins.ps1   # plugins:migrate + tmp:clear + restart"
