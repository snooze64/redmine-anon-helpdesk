# `redmine_hidden_user_profile` インストール手順書

匿名性を担保するためのキープラグイン [JGallot/redmine_hidden_user_profile](https://github.com/JGallot/redmine_hidden_user_profile) を、**Docker 構成の Redmine** に導入するための手順です。

> 本リポジトリの方針として bare-metal インストールは取り扱わず、Docker 構成のみを対象とします。

## 0. 概要

### このプラグインが行うこと

| 機能 | 内容 |
|---|---|
| 新しい権限 `Show user profile` を追加 | ロール毎に「他人のプロフィールページを開けるか」を切替可能 |
| `/users/:id` (ユーザー詳細) を権限ベースで保護 | 権限がない一般ユーザーには **HTTP 403** を返す |
| チケット担当者・ウォッチャー欄等の **ユーザーリンクを delinkify** | 権限がないユーザーが見ると「リンクではなく文字列」になる |
| プロジェクトの「Members」ボックスを非表示 | 権限がないユーザーには表示されない |
| システム管理者は常に閲覧可能 | `view_profiles` 権限の有無に関係なく素通し |

### 動作確認済み環境

| 項目 | 値 |
|---|---|
| Redmine | 5.x / 6.1.x |
| プラグインバージョン | 0.0.4 (default branch `main`、コミット `b604b6c`) |
| Ruby gem 依存 | 無し（Gemfile にエントリーは無く `bundle install` での追加 fetch も不要） |
| DB マイグレーション | 無し（テーブル追加なし） |

### 環境別の選択早見表

| 環境 | 採用パターン |
|---|---|
| Docker（オンライン・ホットリロードしたい） | **§1 パターン A: ボリュームマウント** |
| Docker（イメージに焼く・オンラインビルド） | **§2 パターン B: イメージ内 git clone**（現状の Dockerfile はこれ） |
| Docker（インターネット遮断環境・ビルド時もオフライン） | **§3 パターン C: ベンダリング or イメージ転送** |

> **メール通知設定について**: 本プラグインの動作確認には SMTP 接続は不要ですが、Redmine のメール通知（チケット更新時の watcher 通知等）を併せて検証したい場合は [docs/manual_setup.md §4-1](manual_setup.md#4-1-smtp-の接続先設定ui-からは不可環境変数で切替) を参照し `.env` で SMTP プロバイダを切り替えてください。Mailpit / Gmail / 任意の SMTP サーバーに対応しています。

---

## 1. パターン A: Docker でボリュームマウント

検証用 / プラグインを書き換えながら試したい場合に便利。

### 1-1. ホスト側でプラグインを取得

```bash
mkdir -p <project_root>/plugins
cd <project_root>/plugins
git clone https://github.com/JGallot/redmine_hidden_user_profile.git
```

### 1-2. `docker-compose.yml` に volumes を 1 行追加

```yaml
services:
  redmine:
    # ...
    volumes:
      - redmine6_files:/usr/src/redmine/files
      - ./config/configuration.yml:/usr/src/redmine/config/configuration.yml:ro
      - ./plugins/redmine_hidden_user_profile:/usr/src/redmine/plugins/redmine_hidden_user_profile:ro   # ← 追加
```

> **注意**: 現在の Dockerfile は `git clone` で同じ場所にプラグインを焼き込んでいます。マウントを追加するときは Dockerfile 側の `git clone` 行を削除しないと、コンテナ起動時にディレクトリが衝突します。マウントで運用するなら Dockerfile からは外しましょう。

### 1-3. 起動 + migrate

```powershell
docker compose up -d
docker compose exec -T redmine bundle exec rake redmine:plugins:migrate
docker compose restart redmine
```

→ §4 動作確認へ

---

## 2. パターン B: Docker イメージにプラグインを焼き込む（オンラインビルド）

**現状の本リポジトリの Dockerfile はこの方式です。** ビルドマシンがインターネットに繋がっていれば、ビルド時に GitHub から `git clone` してイメージに含める形になります。

### 2-1. Dockerfile（参考: 既に設定済み）

```dockerfile
FROM redmine:6
USER root
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/JGallot/redmine_hidden_user_profile.git \
        /usr/src/redmine/plugins/redmine_hidden_user_profile \
    && chown -R redmine:redmine /usr/src/redmine/plugins/redmine_hidden_user_profile

USER redmine
```

### 2-2. ビルド & 起動

```powershell
docker compose build
docker compose up -d
docker compose exec -T redmine bundle exec rake redmine:plugins:migrate
docker compose restart redmine
```

→ §4 動作確認へ

---

## 3. パターン C: Docker オフライン環境

ビルド時もインターネットが使えない環境向け。**`git clone` を Dockerfile から取り除いて、ローカルに置いたソースを `COPY` する** 形に切り替えます。または、イメージそのものをオンライン環境でビルドしてオフラインへ転送します。

### 方式 C-1: ソースをベンダリング (`COPY`)

#### C-1-a. インターネット側でソースを取得

ビルドマシン（インターネット可）で 1 度だけ:

```bash
cd <project_root>
mkdir -p plugins
cd plugins
git clone https://github.com/JGallot/redmine_hidden_user_profile.git
# .git は不要なら削除しても OK (リポジトリ容量が膨らむため)
rm -rf redmine_hidden_user_profile/.git
```

> ライセンス上の懸念がある場合（このプラグインは LICENSE ファイル不在）は、自前の Git サーバー（GitLab / Gitea 等）にミラーしてそこから取得する方式をおすすめします。

#### C-1-b. Dockerfile を書き換え

```dockerfile
FROM redmine:6
USER root
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# ↑ git は使わなくなるので削除可

# ベンダリングしたソースを COPY
COPY plugins/redmine_hidden_user_profile /usr/src/redmine/plugins/redmine_hidden_user_profile
RUN chown -R redmine:redmine /usr/src/redmine/plugins/redmine_hidden_user_profile

USER redmine
```

#### C-1-c. オフライン環境で `docker compose build`

```bash
# プロジェクト一式 (Dockerfile, plugins/, scripts/, ...) をオフライン環境に転送
# その後オフラインで:
docker compose build
docker compose up -d
docker compose exec -T redmine bundle exec rake redmine:plugins:migrate
docker compose restart redmine
```

→ §4 動作確認へ

### 方式 C-2: ビルド済みイメージを転送 (`docker save / load`)

ビルドマシンとオフライン環境を分離する方式（イメージのみ転送）:

```bash
# インターネット側 (パターン B でビルドした後)
docker save redmine-redmine:latest -o redmine-image.tar
# ↑ サイズ目安 700MB〜1GB

# 承認済みファイル転送経由でオフラインへ
# オフライン環境側で
docker load -i redmine-image.tar
docker compose up -d
docker compose exec -T redmine bundle exec rake redmine:plugins:migrate
docker compose restart redmine
```

→ §4 動作確認へ

> **Tip**: `mysql:8.0` `axllent/mailpit` 等の依存イメージも同じく `docker save` で持ち込み。

---

## 4. インストール後の動作確認

### 4-1. プラグインが認識されているか

ブラウザで `管理 → プラグイン` を開き **Redmine Hidden User Profile plugin (version 0.0.4)** が表示されること。

### 4-2. 権限が登録されているか

`管理 → ロールと権限` の各ロールの編集画面で **"Show user profile"** チェックボックスが現れていること（プラグインが日本語ロケールを持たないため英語表示）。

または Rails runner で:

```powershell
docker compose exec -T redmine bundle exec rails runner "puts Redmine::AccessControl.permission(:view_profiles).inspect"
```

`#<Redmine::AccessControl::Permission:... @name=:view_profiles ...>` が表示されれば登録成功。`nil` ならプラグイン未読込。

### 4-3. 権限のセットアップ（重要）

> プラグインを入れただけでは何も挙動が変わりません。**ロールごとに `Show user profile` を ON/OFF する必要** があります。

Redmine 既定の `redmine:load_default_data` を実行している場合、Manager ロールには **デフォルトで全権限が付与され、`view_profiles` も含まれてしまいます**。一般ユーザーに見せたくない場合は手動で外してください。

詳細手順: [docs/manual_setup.md §1-3 既存ロールから「Show user profile」権限を外す](manual_setup.md#1-3-既存ロールから-show-user-profile-権限を外す)

### 4-4. HTTP レベルの動作確認

任意の非管理者ユーザー（例: `tester`）でログインし、`/users/<別ユーザーID>` にアクセスして **403 Forbidden** が返れば成功。管理者では 200 OK で開けることを確認。

```powershell
# 例: ローカル検証 (test ユーザーでログイン済の cookie を持っている前提)
curl -b cookie.txt -o NUL -w "HTTP %{http_code}`n" http://localhost:3080/users/1
# HTTP 403 → 期待通り
```

---

## 5. アンインストール

このプラグインには DB マイグレーションが無いので、**ファイル参照を切って再起動するだけ** で済みます。

| パターン | 操作 |
|---|---|
| パターン A | `docker-compose.yml` の `volumes` 行を削除 → `docker compose up -d` |
| パターン B | `Dockerfile` の `RUN git clone ...` 行を削除 → `docker compose build && docker compose up -d` |
| パターン C-1 | `Dockerfile` の `COPY plugins/redmine_hidden_user_profile ...` 行を削除 → 同上 |
| パターン C-2 | プラグインを除去したイメージを再構築 (=パターン B か C-1 で再ビルド) して再転送 |

> **注意**: アンインストールすると `view_profiles` 権限自体が消えるため、各ロールから自動的にチェック状態が外れます（権限設定のロールバックは特に不要）。

---

## 6. トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `管理 → プラグイン` に表示されない | プラグインディレクトリ未配置 / 権限不足 | `docker compose exec -T redmine ls /usr/src/redmine/plugins/redmine_hidden_user_profile/init.rb` で確認 |
| ロール編集画面に **Show user profile** が出てこない | プラグイン未読込（boot 失敗 or 名前ミス） | `docker compose logs redmine` を見る、init.rb のロード時例外を確認 |
| 全ユーザー（管理者でも）が `/users/:id` で 403 | プラグインの内部例外 / 互換性問題 | Redmine ログを確認。バージョンが古い場合は `git pull` でプラグイン更新 |
| 一般ユーザーが他人のプロフィールを依然として見られる | 該当ロールに **Show user profile** が ON | 管理画面でチェックを外す（[manual_setup.md §1-3](manual_setup.md)） |
| `bundle: command not found` | ホスト側で実行している | `docker compose exec -T redmine bundle exec ...` の形でコンテナ内実行 |
| オフライン環境で `git clone` が失敗 | Dockerfile が GitHub から fetch しようとしている | パターン C に切替（COPY 方式 or `docker save`） |

---

## 7. アップデート手順

### 7-1. パターン A (ボリュームマウント)

```powershell
cd plugins\redmine_hidden_user_profile
git pull
cd ..\..
docker compose exec -T redmine bundle exec rake redmine:plugins:migrate
docker compose restart redmine
```

### 7-2. パターン B (オンラインビルド)

Dockerfile の `git clone --depth 1` は HEAD を取るので、再ビルドすれば自動的に最新版になる:

```powershell
docker compose build --no-cache redmine
docker compose up -d
docker compose exec -T redmine bundle exec rake redmine:plugins:migrate
docker compose restart redmine
```

### 7-3. パターン C-1 (ベンダリング)

```bash
cd plugins/redmine_hidden_user_profile
git pull   # インターネット可のビルドマシン側で
# プロジェクト一式をオフライン環境に転送
# その後オフラインで:
docker compose build
docker compose up -d
docker compose exec -T redmine bundle exec rake redmine:plugins:migrate
```

### 7-4. パターン C-2 (イメージ転送)

§3 方式 C-2 と同じ手順で新しい `redmine-image.tar` を作って持ち込み、`docker load` で更新。

---

## 8. 注意点・将来検討事項

| 項目 | 内容 |
|---|---|
| ライセンス未指定 | プラグインリポジトリに LICENSE が無いため、利用先の組織ポリシー次第では再配布不可。ベンダリングする場合は法務確認推奨 |
| メンテナンス頻度 | 現フォーク (JGallot) も極小規模。Redmine 6 でメソッドシグネチャが変わると動作不能になるリスクあり |
| Redmine 7+ 未検証 | 将来 Redmine 7 が出たら独自にパッチが必要になる可能性 |
| 代替案 | `banica/redmine_hide_username`（ユーザー名自体をロール名に置換）も類似機能。ただし要件と合致しないことが多い |
| 認可の二重化 | 本プラグインは「プロフィール画面」と「ユーザーリンク」のみ保護。API (`/users/:id.json` など) のレスポンスはまた別レイヤーの設定が必要な場合あり |

---

以上で `redmine_hidden_user_profile` プラグインのインストール・更新・アンインストールが完了します。
