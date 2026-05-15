# Redmine プラグインの管理

このリポジトリの Redmine は **プラグインを Docker イメージに焼き込まず、ホストの
`./plugins/` を bind-mount で読み込む** 方式 (`docker-compose.yml` 参照)。
追加・更新・削除はホスト側で `git clone` / `git pull` / `rm -rf` するだけで、
再ビルドは不要です。

ただし **DB マイグレーション状態** の管理は別途必要。プラグインを追加・削除した
後は **必ず `./tools/refresh_plugins.{ps1,sh}` を実行** してください
(理由は §4 参照)。

---

## 0. 全体像

```
redmine/
├── Dockerfile                 ← プラグインは含まないが、AI Helper 依存 gem 用の build-essential を追加
├── docker-compose.yml         ← ./plugins:/usr/src/redmine/plugins を bind-mount
├── plugins/                   ← ホスト側でプラグインを置く場所 (gitignore)
│   ├── .gitkeep
│   ├── redmine_hidden_user_profile/   ← git clone で配置
│   ├── view_customize/                ← 同上
│   └── redmine_ai_helper/             ← 同上
├── tools/
│   ├── install_plugins.{ps1,sh}    ← 推奨プラグインを clone / 更新
│   ├── refresh_plugins.{ps1,sh}    ← 追加・更新後に必ず実行
│   └── reset_plugin_state.{ps1,sh} ← 削除後に boot ループする場合の脱出
└── ...
```

| 操作 | コマンド |
|---|---|
| 推奨プラグインを初期取得 | `./tools/install_plugins.ps1` (or `.sh`) |
| プラグイン更新 | `./tools/install_plugins.ps1` (内部で `git pull`) |
| 変更を Redmine に反映 | `./tools/refresh_plugins.ps1` |
| 起動失敗時の復旧 | `./tools/reset_plugin_state.ps1 <plugin_name>` |

---

## 1. 初回セットアップ

```powershell
# 1. リポジトリを clone
git clone https://github.com/snooze64/redmine-anon-helpdesk.git
cd redmine-anon-helpdesk

# 2. .env を準備 (必要に応じて)
Copy-Item .env.example .env
notepad .env

# 3. 推奨プラグインを取得
.\tools\install_plugins.ps1
# → plugins/redmine_hidden_user_profile, plugins/view_customize, plugins/redmine_ai_helper が作られる

# 4. Redmine を起動
docker compose up -d

# 5. プラグインを Redmine 側に反映
.\tools\refresh_plugins.ps1
# → plugins:migrate + tmp:clear + restart
```

これで `管理 → プラグイン` に 3 つのプラグインが表示されれば成功。

---

## 2. プラグインを追加する

### 2-a. 推奨プラグインに追加したい場合

`tools/install_plugins.ps1` (or `.sh`) の `$plugins` 配列に行を足す:

```powershell
$plugins = @(
  @{ name='redmine_hidden_user_profile'; url='https://github.com/JGallot/redmine_hidden_user_profile.git' },
  @{ name='view_customize';              url='https://github.com/onozaty/redmine-view-customize.git'      },
  @{ name='redmine_ai_helper';           url='https://github.com/haru/redmine_ai_helper.git'             },
  @{ name='my_new_plugin';               url='https://github.com/example/my_new_plugin.git'              }   # ← 追加
)
```

再度 `./tools/install_plugins.ps1` を実行 → `./tools/refresh_plugins.ps1` で反映。

### 2-b. 試しに 1 つだけ追加したい場合

スクリプトを編集せずに直接:

```powershell
cd plugins
git clone https://github.com/example/some_plugin.git
cd ..
.\tools\refresh_plugins.ps1
```

特定のタグ・コミットを使いたい場合:

```powershell
git -C plugins\some_plugin checkout v1.2.3
.\tools\refresh_plugins.ps1
```

---

## 3. プラグインを更新する

### 推奨プラグイン全部

```powershell
.\tools\install_plugins.ps1   # 各プラグインで git pull
.\tools\refresh_plugins.ps1   # plugins:migrate + restart
```

### 個別

```powershell
git -C plugins\view_customize pull --ff-only
.\tools\refresh_plugins.ps1
```

---

## 4. なぜ `refresh_plugins` が必要なのか

Redmine プラグインは **DB スキーマを変更する** ものがある (新規テーブルを作る等)。
プラグイン本体を `./plugins/` に置いただけでは Redmine は **新しいテーブルを
作りません**。`bundle exec rake redmine:plugins:migrate` を明示的に実行する
必要があります。

これを忘れると、起動時に "テーブルが存在しないのにモデルが load される" 状態
になり、Redmine の boot が失敗するか、UI で奇妙なエラーが出ます。

`refresh_plugins.ps1` がやっていること:

```
1. docker compose exec redmine bundle exec rake redmine:plugins:migrate
   → 各プラグインの db/migrate/*.rb を実行 (もし未適用のものがあれば)
2. docker compose exec redmine bundle exec rake tmp:clear
   → tmp/cache/ をクリア (旧プラグインのクラス参照キャッシュを除去)
3. docker compose restart redmine
   → Rails サーバーを再起動して新しいクラス階層を fresh load
```

なお **自動実行はしていません**。理由: migration が失敗すると Redmine が
boot ループに陥り、Web UI からの復旧が不可能になるため。手動で実行する方が
失敗時の制御が効きやすいので、明示的なコマンドにしています。

---

## 5. プラグインを削除する

```powershell
# 1. 物理削除
Remove-Item -Recurse -Force plugins\some_plugin

# 2. 反映
.\tools\refresh_plugins.ps1
```

### 削除後に Redmine が起動しない場合 (boot ループ)

プラグインの DB migration 履歴が `plugin_schema_migrations` テーブルに残って
いることが原因。脱出ハッチで履歴を消す:

```powershell
.\tools\reset_plugin_state.ps1 some_plugin
```

このスクリプトは:
1. DB の `plugin_schema_migrations` から `plugin_name LIKE 'some_plugin'` の行を削除
2. `tmp:clear` を実行
3. Redmine を再起動

注: **プラグインが作った実テーブルそのものは残ります** (= データはそのまま)。
不要なら手動で:

```powershell
docker compose exec -T db mysql -uroot -p<root_pw> redmine -e "DROP TABLE some_plugin_data;"
```

---

## 6. オフライン環境での運用

ビルドマシンと実行マシンが分かれていて、実行マシンからインターネットに出ら
れない場合:

### 6-a. ホストの `plugins/` を別マシンで構築 → 持ち込み

```powershell
# インターネット可のマシン上で
.\tools\install_plugins.ps1
Compress-Archive plugins plugins.zip

# 実行マシンに転送 → 展開
Expand-Archive plugins.zip
.\tools\refresh_plugins.ps1
```

このリポジトリの Dockerfile は **インターネットに一切アクセスしない** ように
なっているため、`docker compose build` 自体は実行マシンが redmine ベース
イメージを取得できれば完結します。プラグインの取得経路だけ切り離せる構成です。

### 6-b. プラグインを社内 Git にミラー

外部 GitHub が直接見えない場合は、社内 GitLab/Gitea にミラーしておいて、
`install_plugins.ps1` の URL を社内ホストに書き換える:

```powershell
$plugins = @(
  @{ name='redmine_hidden_user_profile'; url='https://git.example.internal/mirrors/redmine_hidden_user_profile.git' },
  ...
)
```

---

## 7. トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `管理 → プラグイン` にプラグインが出てこない | bind-mount が効いていない / プラグインディレクトリが空 | `docker compose exec -T redmine ls /usr/src/redmine/plugins/` で確認 |
| Redmine が boot ループする (`docker compose logs redmine` がエラー繰り返し) | プラグイン migration が未適用 or プラグインを削除後の DB 残骸 | `./tools/refresh_plugins.ps1` → だめなら `./tools/reset_plugin_state.ps1 <name>` |
| `redmine_ai_helper` 追加後に `You have to install development tools first` | AI Helper の依存 gem が native extension をビルドするため、コンパイラが必要 | `Dockerfile` に `build-essential` を入れて `docker compose build redmine` → `docker compose up -d redmine` |
| AI Helper の `OpenAI-Organization header should match organization for API key` | モデルプロファイルの `Organization ID` が API key の所属組織と一致していない | `Organization ID` を空欄にするか、OpenAI Platform の `org-...` ID を入れる |
| `tmp:clear` が `Permission denied` | bind-mount の権限問題 (ホストの umask 等) | `chmod -R o+r plugins/` で読み権限を与える (Linux ホストの場合) |
| プラグインが UI には出るが機能しない | `plugins:migrate` 未実行 / Rails サーバー未再起動 | `./tools/refresh_plugins.ps1` を再実行 |
| プラグインを更新したのに古い挙動のまま | bootsnap キャッシュが残存 | `./tools/refresh_plugins.ps1` 内の `tmp:clear` で消える |
| Windows で `git clone` が `Filename too long` | パスが 260 文字制限超え | `git config --system core.longpaths true` |
| `bundle: command not found` | ホスト側で実行している | `docker compose exec -T redmine bundle exec ...` の形でコンテナ内実行 |

### 最終手段: 完全リセット (データも消える、注意)

プラグイン関連でどうにもならなくなった場合の核オプション:

```powershell
docker compose down -v   # MySQL ボリュームごと削除 — 全データ消失!
.\tools\install_plugins.ps1
docker compose up -d
.\tools\refresh_plugins.ps1
# 初期セットアップ (docs/manual_setup.md) からやり直し
```

開発・検証環境専用。本番では絶対に使わないこと。

---

## 8. プラグイン別メモ

### 8-1. `redmine_hidden_user_profile` ([JGallot fork](https://github.com/JGallot/redmine_hidden_user_profile))

匿名性のためのキープラグイン。一般ユーザーから `/users/:id` を 403 にし、
ユーザーリンクをプレーンテキスト化、プロジェクトの "Members" 欄も非表示にする。

| 項目 | 値 |
|---|---|
| Redmine 互換 | 5.x / 6.1.x |
| DB マイグレーション | **無し** (テーブル追加なし) |
| Gemfile 追加 | 無し |
| ライセンス | LICENSE ファイル不在 (利用先組織のポリシー確認推奨) |

セットアップ後は **ロールごとに「Show user profile」権限の ON/OFF** が必要
([docs/manual_setup.md §1-3](manual_setup.md))。デフォルトデータをロードした
直後は Manager ロールに自動で付与されているので注意。

### 8-2. `view_customize` ([onozaty/redmine-view-customize](https://github.com/onozaty/redmine-view-customize))

任意の URL パターンに対して JavaScript / CSS を注入できるプラグイン。本リポ
ジトリでは「質問者ロールには『+ 新しいチケット』を表示しない」目的で使う
(Mode C: チャットボット経由起票への誘導)。

| 項目 | 値 |
|---|---|
| Redmine 互換 | 4.x / 5.x / 6.x |
| DB マイグレーション | **有り** (`view_customizes` テーブルを作る) |
| Gemfile 追加 | 無し |
| ライセンス | MIT |

設置後の JS ルール登録手順は [docs/view_customize_setup.md](view_customize_setup.md) 参照。

### 8-3. `redmine_ai_helper` ([haru/redmine_ai_helper](https://github.com/haru/redmine_ai_helper))

Redmine 画面に AI chat / issue summary / reply draft / sub issue draft / project health report などを追加するプラグイン。
本リポジトリでは非商用系の AI 支援プラグインとして host bind-mount 方式で導入する。

| 項目 | 値 |
|---|---|
| Redmine 互換 | 6.0+ |
| 導入済みバージョン | 3.1.1 |
| DB マイグレーション | **有り** (`ai_helper_*` テーブルを作る) |
| Gemfile 追加 | **有り** (`ruby_llm`, `ruby_llm-mcp`, `mcp`, `langfuse`, `qdrant-ruby` など) |
| Dockerfile 追加 | `build-essential` (native extension gem のビルド用) |
| ライセンス | MIT |

初期設定では `管理 → AI Helper` から model profile を作成する。
OpenAI を使う場合は、まず以下の設定が無難。

| 項目 | 推奨値 |
|---|---|
| Type | `OpenAI` |
| Name | 任意 (`OpenAI GPT-4.1 mini` など) |
| Access key | OpenAI API key |
| Organization ID | 空欄 (複数組織を明示したい場合のみ `org-...`) |
| Model name | `gpt-4.1-mini` |
| Temperature | `0.3`〜`0.7` |

ロール権限は `管理 → ロールと権限` で設定する。

| ロール | 推奨権限 |
|---|---|
| Manager / 管理寄りロール | `View AI Helper`, `Settings AI Helper`, `Delete AI Helper health reports` |
| Developer / Reporter | `View AI Helper` |
| Anonymous / Non member | 原則付与しない |

各プロジェクトで利用するには、`プロジェクト → 設定 → モジュール` で **AI Helper** を有効化する。
詳細は [redmine_ai_helper_setup.md](redmine_ai_helper_setup.md) 参照。

---

## 9. アンインストール (= host-mount 方式自体をやめたい場合)

このリポジトリの方針 (host bind-mount) を捨てて Dockerfile に焼き込み運用に
戻したい場合は:

1. `Dockerfile` に `RUN git clone --depth 1 ... /usr/src/redmine/plugins/<name>` を追加
2. `docker-compose.yml` の `- ./plugins:/usr/src/redmine/plugins` 行を削除
3. `docker compose build && docker compose up -d`

ただし「プラグイン入替に再ビルドが要る」「Dockerfile がプラグインに縛られ
る」というデメリットが復活するため、特に理由がなければ host-mount 方式の
ままが推奨です。
