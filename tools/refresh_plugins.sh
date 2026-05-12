#!/usr/bin/env bash
# プラグインを ./plugins/ に出し入れした後、変更を Redmine に反映する。
# PowerShell 版の refresh_plugins.ps1 と等価。詳細はそちらのヘッダ参照。

set -euo pipefail

echo "[1/3] plugins:migrate..."
docker compose exec -T redmine bundle exec rake redmine:plugins:migrate RAILS_ENV=production

echo ""
echo "[2/3] tmp:clear..."
docker compose exec -T redmine bundle exec rake tmp:clear RAILS_ENV=production

echo ""
echo "[3/3] restart redmine..."
docker compose restart redmine

sleep 3

echo ""
echo "--- 直近ログ ---"
docker compose logs --tail 20 redmine
