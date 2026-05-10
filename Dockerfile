FROM redmine:6

# プロキシ環境向け build args (.env で HTTP_PROXY/http_proxy 等を設定すると docker-compose 経由で渡る)
# BuildKit は ARG として宣言された HTTP_PROXY 系を自動的に RUN 時の環境変数にも昇格させる
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

# USER について:
#   - redmine:6 のベースイメージはデフォルトで root 起動なので USER root は不要
#   - 末尾の USER redmine は必須:
#     redmine の entrypoint は root で起動すると /usr/src/redmine/config/
#     配下を chown しようとするため、read-only マウントしている
#     configuration.yml と衝突して起動ループに陥る。
#     redmine ユーザーで起動すれば entrypoint が当該 chown をスキップする。

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Hidden User Profile plugin — 一般ユーザーから /users/:id を 403 にし、
# チケット担当者・ウォッチャー等のプロフィールリンクをプレーンテキスト化、
# プロジェクトの "Members" 欄も非表示にする。
# ロール権限 view_profiles で表示可否を切替。管理者は常に見られる。
RUN git clone --depth 1 https://github.com/JGallot/redmine_hidden_user_profile.git \
        /usr/src/redmine/plugins/redmine_hidden_user_profile \
    && chown -R redmine:redmine /usr/src/redmine/plugins/redmine_hidden_user_profile

USER redmine

# 初期セットアップは docs/manual_setup.md（管理画面手順）を参照。
# 自動化したい場合はホスト側で scripts/seed.rb 等を用意し、
# `docker compose exec -T redmine bundle exec rails runner -` の標準入力経由か
# `docker cp` で投入してください。
