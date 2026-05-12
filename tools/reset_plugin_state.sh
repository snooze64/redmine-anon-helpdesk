#!/usr/bin/env bash
# プラグインを物理削除した後、Redmine が boot ループする場合の脱出ハッチ。
# PowerShell 版の reset_plugin_state.ps1 と等価。詳細はそちらのヘッダ参照。
#
# 使い方:
#   ./tools/reset_plugin_state.sh redmine_some_plugin

set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "usage: $0 <plugin_name>" >&2
  exit 1
fi
plugin="$1"

root="$(cd "$(dirname "$0")/.." && pwd)"

# .env から MySQL の認証情報を取り出す (簡易)
get_env() {
  local key="$1"; local fallback="$2"; local val=""
  if [ -f "$root/.env" ]; then
    val=$(grep -E "^${key}=" "$root/.env" | head -1 | cut -d= -f2-)
  fi
  echo "${val:-$fallback}"
}

db=$(get_env MYSQL_DATABASE redmine)
user=$(get_env MYSQL_USER redmine)
pass=$(get_env MYSQL_PASSWORD redmine_pw)

echo "DB '$db'.plugin_schema_migrations から plugin_name LIKE '$plugin' を削除..."
docker compose exec -T db mysql -u "$user" -p"$pass" "$db" \
  -e "DELETE FROM plugin_schema_migrations WHERE plugin_name LIKE '${plugin}';"

echo ""
echo "tmp:clear (失敗しても継続)..."
docker compose exec -T redmine bundle exec rake tmp:clear RAILS_ENV=production || true

echo ""
echo "restart redmine..."
docker compose restart redmine

sleep 3
echo ""
echo "--- 直近ログ ---"
docker compose logs --tail 30 redmine
