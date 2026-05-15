# Redmine 本体のみ。
# プラグインはイメージに焼き込まず、ホストの ./plugins/ を
# bind-mount してコンテナから参照する方式 (docker-compose.yml 参照)。
# 利点:
#   - プラグインの追加 / 更新 / 削除に再ビルドが要らない
#   - オフライン環境では別マシンで clone → zip 持込み → ./plugins に展開、で OK
#   - Dockerfile が固定プラグインに縛られない
# プラグイン管理ワークフローは docs/plugin_install.md 参照。

FROM redmine:6

USER root

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# USER について:
#   - redmine:6 のベースイメージはデフォルトで root 起動なので USER root は不要
#   - 末尾の USER redmine は必須:
#     redmine の entrypoint は root で起動すると /usr/src/redmine/config/
#     配下を chown しようとするため、read-only マウントしている
#     configuration.yml と衝突して起動ループに陥る。
#     redmine ユーザーで起動すれば entrypoint が当該 chown をスキップする。
USER redmine

# 初期セットアップは docs/manual_setup.md（管理画面手順）を参照。
# 自動化したい場合はホスト側で scripts/seed.rb 等を用意し、
# `docker compose exec -T redmine bundle exec rails runner -` の標準入力経由か
# `docker cp` で投入してください。
