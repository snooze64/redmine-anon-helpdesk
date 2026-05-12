#!/usr/bin/env bash
# 推奨プラグインを ./plugins/ に取得する (clone または git pull で更新)。
# PowerShell 版の install_plugins.ps1 と等価。詳細はそちらのヘッダ参照。
# 取得後: docker compose up 後に ./tools/refresh_plugins.sh を実行。

set -euo pipefail

# (name url) の組。pin したい場合は git -C plugins/<name> checkout <tag> を別途。
PLUGINS=(
  "redmine_hidden_user_profile https://github.com/JGallot/redmine_hidden_user_profile.git"
  "view_customize              https://github.com/onozaty/redmine-view-customize.git"
)

root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$root/plugins"

for entry in "${PLUGINS[@]}"; do
  name=$(echo "$entry" | awk '{print $1}')
  url=$(echo "$entry" | awk '{print $2}')
  dst="$root/plugins/$name"
  if [ -d "$dst/.git" ]; then
    echo "[$name] git pull..."
    git -C "$dst" pull --ff-only
  else
    echo "[$name] git clone..."
    git clone --depth 1 "$url" "$dst"
  fi
done

echo ""
echo "完了。次に以下を実行してください:"
echo "  docker compose up -d"
echo "  ./tools/refresh_plugins.sh   # plugins:migrate + tmp:clear + restart"
