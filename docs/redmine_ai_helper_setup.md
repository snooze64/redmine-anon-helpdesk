# Redmine AI Helper セットアップメモ

この文書は `haru/redmine_ai_helper` を本リポジトリの Redmine 6 環境に追加した後の設定メモです。
プラグイン本体の取得と migration は [plugin_install.md](plugin_install.md) を参照してください。

## 導入内容

追加プラグイン:

- `redmine_ai_helper`  
  Repository: https://github.com/haru/redmine_ai_helper  
  導入時バージョン: `3.1.1`

Redmine 側で確認済みのプラグイン一覧:

- `redmine_ai_helper:3.1.1`
- `redmine_hidden_user_profile:0.0.4`
- `view_customize:3.5.4`

`redmine_ai_helper` は `ruby_llm` などの gem を追加します。一部 gem は native extension をビルドするため、`Dockerfile` に `build-essential` を追加しています。

## 起動・反映

プラグイン追加後は以下を実行します。

```powershell
docker compose build redmine
docker compose up -d redmine
.\tools\refresh_plugins.ps1
```

`refresh_plugins.ps1` は以下を行います。

- `redmine:plugins:migrate`
- `tmp:clear`
- `docker compose restart redmine`

## モデルプロファイル

`管理 → AI Helper` で model profile を作成します。

OpenAI を使う場合の初期値:

| 項目 | 値 |
|---|---|
| Type | `OpenAI` |
| Name | 任意 (`OpenAI GPT-4.1 mini` など) |
| Access key | OpenAI API key |
| Organization ID | 空欄推奨 |
| Model name | `gpt-4.1-mini` |
| Temperature | `0.3`〜`0.7` |

`Organization ID` は通常は空欄でよいです。入力する場合は OpenAI Platform の `org-...` 形式の ID を使います。
API key の所属組織と一致しない値を入れると `OpenAI-Organization header should match organization for API key` が発生します。

## ロール権限

`管理 → ロールと権限` で AI Helper 関連権限を付与します。

| ロール | 推奨権限 |
|---|---|
| Manager / 管理者相当 | `View AI Helper`, `Settings AI Helper`, `Delete AI Helper health reports` |
| Developer | `View AI Helper` |
| Reporter | 必要に応じて `View AI Helper` |
| Anonymous / Non member | 原則付与しない |

権限の意味:

- `View AI Helper`: チャット、チケット要約、返信案、サブチケット案、プロジェクト健康診断などを使う権限。
- `Settings AI Helper`: プロジェクト単位の AI Helper 設定を変更する権限。
- `Delete AI Helper health reports`: 生成済み健康診断レポートを削除する権限。

## プロジェクト側の有効化

ロール権限だけでは表示されません。利用するプロジェクトごとに以下を設定します。

1. `プロジェクト → 設定`
2. `モジュール`
3. `AI Helper` にチェック
4. 保存

## MCP について

起動ログに以下の警告が出ることがあります。

```text
MCP config file not found: /usr/src/redmine/config/ai_helper/config.json
```

MCP 連携を使わない場合は警告扱いで問題ありません。
MCP server を使う場合は `/usr/src/redmine/config/ai_helper/config.json` に MCP server 定義を追加します。

## 動作確認

Redmine コンテナ内で読み込まれているプラグインを確認します。

```powershell
docker compose exec -T redmine bundle exec rails runner `
  "puts Redmine::Plugin.all.map { |p| [p.id, p.version].join(':') }" -e production
```

期待する出力例:

```text
redmine_ai_helper:3.1.1
redmine_hidden_user_profile:0.0.4
view_customize:3.5.4
```

Web 側は `http://localhost:3080` が HTTP 200 を返せば起動確認として十分です。
