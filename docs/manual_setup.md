# Redmine 手動セットアップ手順書

Redmine の Web UI だけで「質問者・回答者ロール定義」「View Profiles を回答者だけに付与」「サンプルデータ投入」「規定の通知設定」を行うための手順書です。

> 本ドキュメントは UI 操作だけで構築するときの参照です。同等の処理を Rails スクリプトで自動化したい場合はローカルに `scripts/seed.rb` 等を別途作成してください（リポジトリには機密情報を含むため含めていません）。

---

## 0. 前提

- Redmine 6 系が稼働している（例: http://localhost:3080）
- **既定構成データがロード済み**である（手順は §0-1 参照）
- システム管理者 (`admin`) でログイン可能（初回は `admin / admin` → パスワード変更画面が出るので任意のパスワードに変更）
- 言語が日本語に設定されている（個人設定 → 言語: Japanese）
- プラグイン `redmine_hidden_user_profile` がインストール済み（`管理 → プラグイン` に表示される）。これがないと **「Show user profile」**（=プロフィールの閲覧）権限が出てきません
  - 注: このプラグインには日本語ロケールが含まれていないため、UI 上は **英語のまま「Show user profile」** と表示されます
- AI Helper を使う場合は、プラグイン `redmine_ai_helper` がインストール済み（`管理 → プラグイン` に表示される）。モデル設定・ロール権限・プロジェクトモジュールの有効化は [redmine_ai_helper_setup.md](redmine_ai_helper_setup.md) 参照。

### 0-1. 既定構成データのロード（初回のみ）

新規構築直後の Redmine は **ロール・トラッカー・チケットの状態・優先度・ワークフロー等が空** の状態です。これらが無いと §1 以降の操作（既存ロールへの権限付与、チケット作成等）ができないため、最初に Redmine 標準の既定データをロードします。

**方法 A: Web UI から（推奨）**

1. ブラウザで http://localhost:3080 にアクセス
2. `admin / admin` でログイン → パスワード変更を求められたら任意のパスワードに変更
3. 上部メニュー **管理 → 設定 → 既定構成のロード**（Administration → Settings → Load the default configuration）
4. 言語を `Japanese (日本語)` 選択 → **適用**
5. 「既定構成データが無事ロードされました」と表示されれば完了

**方法 B: コマンドラインから（Docker 構成の場合）**

```powershell
docker compose exec -T -e REDMINE_LANG=ja redmine bundle exec rake redmine:load_default_data
```

> 既にロード済みの環境で再実行しても、データが壊れない代わりに「すでにデータが存在します」と止まるため安全に何度でも試せます。

#### ロードされる主な要素

| カテゴリ | 内容 |
|---|---|
| ロール | Manager / Developer / Reporter |
| チケットの状態 | 新規 / 進行中 / 解決 / フィードバック / 終了 / 却下 |
| トラッカー | バグ / 機能 / サポート |
| 優先度 | 低い / 通常（既定） / 高め / 急いで / 今すぐ |
| 作業時間の分類 | 設計作業 / 開発作業 |
| 文書カテゴリ | 利用者文書 / 技術文書 |
| ワークフロー | 各ロール × 各トラッカーの状態遷移許可表 |

> 英語表示の場合: 表中のラベルは下表で読み替えてください。
>
> | 日本語 | 英語 |
> |---|---|
> | 管理 | Administration |
> | ロールと権限 | Roles and permissions |
> | 新しいロール | New role |
> | チケットの可視性 | Issues visibility |
> | プライベートチケット以外 | Issues are public except private ones |
> | すべてのチケット | All issues |
> | （日本語ロケールなし） | Show user profile |
> | プロジェクト | Projects |
> | 新しいユーザー | New user |
> | 設定 | Settings |
> | メール通知 | Email notifications |
> | 送信元メールアドレス | Emission email address |
> | デフォルトのメール通知オプション | Default notification option |
> | ウォッチ中または自分が関係しているもの | Only for things I watch or I'm involved in |

---

## 1. ロール作成

### 1-1. 質問者ロール

1. ヘッダ右上 **管理** → 左メニュー **ロールと権限**
2. 右上 **新しいロール** をクリック
3. 以下を入力:

   | 項目 | 値 |
   |---|---|
   | 名称 | `質問者` |
   | 説明 | （空欄で OK） |
   | 担当者にできる | **チェックする** |
   | 既定で表示するクエリ | （空欄） |
   | チケットの可視性 | **プライベートチケット以外** |
   | 作業時間の可視性 | すべての作業時間 |
   | ユーザーの可視性 | すべてのアクティブなユーザー |

4. 下部「権限」セクションは **以下の 4 つだけ** チェックして他は外す:
   - **チケットトラッキング** > **チケットの閲覧**
   - **チケットトラッキング** > **チケットの追加**
   - **チケットトラッキング** > **コメントの追加**
   - **チケットトラッキング** > **ウォッチャー一覧の閲覧**

   > **「チケットの追加」を含める理由**: チャットボット (Mode C) がエスカレーション
   > 時に、Redmine API の `X-Redmine-Switch-User` 機能で「質問者本人」になりすま
   > して起票します。これにより質問者が **自分の private チケットだけは** 閲覧可能
   > になります (`author == self` のため)。質問者ロールに `add_issues` 権限が無い
   > と、なりすまし起票が 403 で失敗します。
   >
   > UI 経由の直接起票を抑止したい場合は、`view_customize` プラグインで「+ 新しい
   > チケット」ボタンを非表示にします。手順は [docs/view_customize_setup.md](view_customize_setup.md) 参照。

5. **【重要・忘れがち】「チケットの追加」のすぐ下に出る「トラッカー」マトリックス**
   で、Bug / Feature / Support **すべての列** にチェックを入れる
   (または **「全て」** 列にチェック)。
   - これを忘れると `permissions_all_trackers["add_issues"]` が `"0"` のまま、
     かつ `permissions_tracker_ids["add_issues"]` も空になり、Redmine が
     `Issue.allowed_target_trackers` を空と判定する
   - 結果として「権限はある」のに「+ 新しいチケット」ボタンが UI で出ず、
     **チャットボットからの impersonate 起票も同じ理由で 403** になる
   - 同様のことを `delete_issues` / `edit_issues` を有効にした他のロールでも
     チェックすること
   - 確認用 Rails 1-liner:
     ```bash
     docker compose exec -T redmine bundle exec rails runner \
       'puts Role.find_by(name: "質問者").permissions_all_trackers["add_issues"]'
     # → "1" が出れば OK、"0" なら未許可
     ```

6. ページ下部 **作成** をクリック

### 1-2. 回答者ロール

1. **管理 → ロールと権限 → 新しいロール**
2. 入力:

   | 項目 | 値 |
   |---|---|
   | 名称 | `回答者` |
   | 担当者にできる | **チェックする** |
   | チケットの可視性 | **すべてのチケット** |
   | 作業時間の可視性 | すべての作業時間 |
   | ユーザーの可視性 | すべてのアクティブなユーザー |

3. 「権限」セクションの **すべてのチェックボックスを ON** にする
   - ヒント: ブラウザの開発ツールでまとめて切り替えるか、地道にチェックする
   - **「Show user profile」が含まれていることを確認**（hidden_user_profile プラグイン由来の権限）

4. **作成**

### 1-3. 既存ロールから「Show user profile」権限を外す

`回答者` 以外のロール（管理者ユーザーは権限関係なく見られるので除外不要）から `view_profiles` を剥奪します。

対象: **管理者**（=Manager） / **開発者**（=Developer） / **報告者**（=Reporter） / **非メンバー** / **匿名ユーザー**

各ロールについて以下を実施:

1. **管理 → ロールと権限**
2. ロール名をクリック
3. 「Show user profile」の **チェックを外す**
4. 下部 **保存**

> hidden_user_profile プラグインを入れた直後、デフォルトデータをロードした初期環境では Manager にこの権限が自動付与されているのでとくに注意してください。

### 1-4. 確認

`管理 → ロールと権限` 一覧で各ロールをクリックし以下を確認:

| ロール | Show user profile |
|---|---|
| 管理者 (Manager) | ❌ |
| 開発者 (Developer) | ❌ |
| 報告者 (Reporter) | ❌ |
| 非メンバー | ❌ |
| 匿名ユーザー | ❌ |
| **回答者** | **✅** |
| 質問者 | ❌ |

---

## 2. ユーザー作成

### 2-1. 質問者ユーザー

1. **管理 → ユーザー → 新しいユーザー**
2. 入力:

   | 項目 | 値 |
   |---|---|
   | ログインID | `questioner` |
   | 名 | `Q` |
   | 姓 | `Asker` |
   | メールアドレス | `questioner@example.com`（実受信したいなら自分のアドレスへ） |
   | 言語 | Japanese |
   | システム管理者 | OFF |
   | パスワード | （任意） |
   | パスワード確認 | （同じ） |
   | 次回ログイン時にパスワード変更を強制 | OFF |
   | メール通知 | **ウォッチ中または自分が関係しているもの** |

3. **作成**

### 2-2. 回答者ユーザー

同様に以下で作成:

| 項目 | 値 |
|---|---|
| ログインID | `responder` |
| 名 | `R` |
| 姓 | `Answerer` |
| メールアドレス | `responder@example.com` |
| メール通知 | ウォッチ中または自分が関係しているもの |

---

## 3. プロジェクト作成

### 3-1. デモプロジェクト

1. ヘッダ **プロジェクト** → 右上 **新しいプロジェクト**
2. 入力:

   | 項目 | 値 |
   |---|---|
   | 名称 | `Demo Project` |
   | 説明 | （任意） |
   | 識別子 | `demo` |
   | 公開 | OFF（メンバー以外には見せない） |
   | モジュール | **チケットトラッキング** を ON（他は任意） |
   | トラッカー | 全選択 |

3. **作成**

### 3-2. メンバー追加

1. プロジェクト一覧で **Demo Project** を開く
2. タブ **設定** → サイドバー **メンバー** → 右上 **新しいメンバー**
3. ユーザー検索欄に `questioner` と入力 → チェック → ロール `質問者` → **追加**
4. 同様に `responder` をロール `回答者` で追加

---

## 4. メール通知設定

### 4-1. SMTP の接続先設定（UI からは不可、環境変数で切替）

> **重要**: SMTP サーバーへの接続先は Web UI からは設定できません。本リポジトリの [config/configuration.yml](../config/configuration.yml) は ERB テンプレートになっており、`.env` の環境変数で接続先を切り替える設計です。**`config/configuration.yml` 自体を編集する必要はありません。**

3 種類のプリセットがあります。

#### 4-1-a. 開発・検証用（Mailpit、既定）

`.env` に `SMTP_PROVIDER` を設定しない、または明示的に:

```ini
SMTP_PROVIDER=mailpit
```

Mailpit コンテナが SMTP を受信し、http://localhost:8025 で全メールを閲覧できます。外部にメールが出ないので開発時に安全です。

**Mailpit を使わない（本番運用等）場合**: docker-compose.yml の以下 2 箇所をコメントアウトしてください。

1. **`services:` 直下の `mailpit:` サービスブロック全体**
2. **`redmine:` の `depends_on:` 配下の `mailpit:` 3 行**（`condition: service_started` と `required: false` を含む）

`required: false` だけでは「未定義サービスへの参照」エラーで Compose のパースに失敗するため、両方コメントアウトが必要です。詳細は [.env.example](../.env.example) のコメント参照。

#### 4-1-b. Gmail SMTP（個人検証や小規模向け）

```ini
SMTP_PROVIDER=gmail
GMAIL_USER=your.address@gmail.com
GMAIL_APP_PASSWORD=abcdefghijklmnop   # 16桁のアプリパスワード
SMTP_FROM=your.address@gmail.com      # 通常 GMAIL_USER と同じにする
```

前提:
- Google アカウントで 2 段階認証が ON
- https://myaccount.google.com/apppasswords でアプリパスワードを発行済み
- 送信上限: 個人 Gmail で 1 日 500 通、Workspace で 2000 通

#### 4-1-c. 任意の SMTP サーバー（汎用 / 本番運用向け）

自前のメールリレー、SendGrid、Amazon SES、Postfix、Office 365 など、**SMTP プロトコルで受け付けるサーバーであれば全て** この方式で接続できます。

最低限の設定:

```ini
SMTP_PROVIDER=custom
SMTP_HOST=smtp.example.com
SMTP_PORT=25
SMTP_DOMAIN=example.com
SMTP_FROM=redmine@example.com
```

認証あり / TLS ありの一般的な構成:

```ini
SMTP_PROVIDER=custom
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_DOMAIN=example.com
SMTP_USER=svc-redmine
SMTP_PASSWORD=<service-account password>
SMTP_AUTH=login            # login / plain / cram_md5 のいずれか
SMTP_STARTTLS=true
SMTP_TLS_VERIFY=peer       # 自己署名証明書を相手にする場合は none
SMTP_FROM=redmine@example.com
```

利用可能な環境変数の一覧:

| 変数 | 用途 | 既定値 |
|---|---|---|
| `SMTP_HOST` | SMTP サーバーのホスト名/IP | `localhost` |
| `SMTP_PORT` | SMTP ポート（25/465/587 等） | `25` |
| `SMTP_DOMAIN` | HELO/EHLO で名乗るドメイン名 | `localhost` |
| `SMTP_USER` | 認証ユーザー名（**空なら認証なし**） | （空） |
| `SMTP_PASSWORD` | 認証パスワード | （空） |
| `SMTP_AUTH` | `login` / `plain` / `cram_md5` | `login` |
| `SMTP_STARTTLS` | STARTTLS する: `true` / `false` | `false` |
| `SMTP_TLS_VERIFY` | 証明書検証 `peer`（厳格）/ `none`（無視） | `none` |
| `SMTP_OPENSSL_CA_FILE` | 信頼する CA 証明書のパス（コンテナ内）。プライベート CA を使う場合のみ指定 | （空） |
| `SMTP_FROM` | 送信元アドレス（後述 §4-2 で UI に同じ値を入れる） | `redmine@example.local` |

代表的な接続先のテンプレート例:

| 接続先 | host / port / 認証方式 |
|---|---|
| 自前のメールリレー | `smtp.<own>.com` / 25 / 認証なし or login |
| プライベート CA を使う認証付き SMTP | 587 / login / STARTTLS / `SMTP_OPENSSL_CA_FILE` 指定 |
| SendGrid | `smtp.sendgrid.net` / 587 / login (`SMTP_USER=apikey`、`SMTP_PASSWORD=<API key>`) / STARTTLS |
| Amazon SES (SMTP) | `email-smtp.<region>.amazonaws.com` / 587 / login / STARTTLS |
| Office 365 (SMTP AUTH) | `smtp.office365.com` / 587 / login / STARTTLS |

#### 4-1-d. 反映と確認

1. `.env` を保存
2. コンテナを再作成して環境変数を反映:
   ```powershell
   docker compose up -d
   ```
3. Redmine が実際に保持している smtp_settings を確認:
   ```powershell
   docker compose exec -T redmine bundle exec rails runner "puts ActionMailer::Base.smtp_settings.inspect"
   ```
4. §4-4「動作確認」のテストメール送信が成功すれば疎通 OK

#### 4-1-e. プライベート CA 証明書を使う場合の追記

SMTP サーバーがプライベート CA で署名された証明書を使っている場合、ホスト側の証明書ファイルをコンテナにマウントする必要があります。`docker-compose.yml` の `redmine` サービスの `volumes` に追加:

```yaml
volumes:
  - ./certs/private-ca.crt:/usr/src/redmine/files/private-ca.crt:ro
```

`.env` で参照:

```ini
SMTP_TLS_VERIFY=peer
SMTP_OPENSSL_CA_FILE=/usr/src/redmine/files/private-ca.crt
```

### 4-2. 送信ポリシー（UI で設定）

1. **管理 → 設定**
2. タブ **メール通知**
3. 入力:

   | 項目 | 値 |
   |---|---|
   | 送信元メールアドレス | `redmine@example.local`（Gmail SMTP を使う場合は Gmail のアドレス） |
   | デフォルトのメール通知オプション | **ウォッチ中または自分が関係しているもの** |
   | メールのヘッダ | （任意） |
   | メールのフッタ | （任意） |
   | 件名にチケットの状態を含める | お好み |
   | 「通知するイベント」 | 下記参照 |

4. **通知するイベント** で以下にチェック:
   - チケットが追加された
   - チケットが更新された
   - チケットにコメントが追加された
   - 状態が変更された
   - 担当者が変更された
   - 優先度が変更された

5. ページ下部 **保存**

### 4-3. ホスト名の設定（メール本文中のリンクに使用）

1. **管理 → 設定 → 全般**
2. **ホスト名とパス** に `localhost:3080`（本番では実ホスト名）
3. **プロトコル** を `HTTP`（HTTPS なら HTTPS）
4. **保存**

### 4-4. 動作確認

1. **管理 → 設定 → メール通知**
2. ページ下部 **テストメール送信** リンクをクリック
3. 「`<管理者のメール>` 宛にメールを送信しました」と表示されれば OK
4. メールが届いていれば SMTP 接続成功

---

## 5. サンプルチケット作成

回答者がチケットを起票し、質問者をウォッチャーに登録する想定です。

### 5-1. responder としてログインし直す

1. 右上 **ログアウト**
2. ログインID `responder` で再ログイン

### 5-2. 1 件目: ログインできなくなった

1. **Demo Project** を開く
2. タブ **新しいチケット**
3. 入力:

   | 項目 | 値 |
   |---|---|
   | トラッカー | バグ |
   | 題名 | `ログインできなくなった` |
   | 説明 | （以下） |
   | 優先度 | 通常 |
   | 担当者 | （空でも可） |
   | プライベート | OFF |

   説明欄:
   ```
   質問者からの問い合わせ:
   昨日まで使えていたが、今朝からログインできない。
   パスワードを忘れた可能性。

   【対応メモ】
   - パスワード再発行リンクを案内
   - 改めて状況確認予定
   ```

4. ページ下部 **ウォッチャー** セクション → **追加** → ユーザー検索で `questioner` を選択 → **追加**
5. **作成**

### 5-3. 2 件目: 勤怠システムの月次締め日を変更したい

同手順で作成:

| 項目 | 値 |
|---|---|
| 題名 | `勤怠システムの月次締め日を変更したい` |
| 説明 | 「月末締めから 25 日締めに変更したい。影響範囲・スケジュールの調整が必要。」 |
| ウォッチャー | questioner |

### 5-4. 3 件目: ドキュメントの公開設定を見直したい

| 項目 | 値 |
|---|---|
| 題名 | `ドキュメントの公開設定を見直したい` |
| 説明 | 「取引先にも一部公開したいが、機密情報は出したくない。公開範囲のルール整備を依頼。」 |
| ウォッチャー | questioner |

---

## 6. 動作確認

### 6-1. 質問者の閲覧範囲

1. `responder` でログアウト → `questioner` で再ログイン
2. **Demo Project → チケット** に作成した 3 件すべてが表示されること
3. 任意のチケットを開き右側 **ウォッチャー (2)** に自分が含まれること
4. URL に `/users/<回答者のID>` を直接入力（例: `http://localhost:3080/users/7`）→ **403 Forbidden** が返ること
5. 自分自身のプロフィール `http://localhost:3080/users/<自分のID>` も **403** になること（hidden_user_profile の仕様）

### 6-2. 回答者の閲覧範囲

1. `responder` でログイン
2. URL に `/users/<質問者のID>`（例: `http://localhost:3080/users/6`）→ **200 表示**
3. プロフィールページに「**ログインID: questioner**」が表示されること（=回答者は把握可能）

### 6-3. 質問者がコメント追加できること

1. `questioner` で `Demo Project → ログインできなくなった (#X)` を開く
2. ページ下部 **コメント** または右上 **編集** → 「コメント」欄に何か書いて **送信**
3. ページがリロードされ、自分のコメントが履歴に追加されていること

### 6-4. メール通知

1. `responder` で同チケットにコメント追加
2. 質問者に登録されているメールアドレスに通知が届く
   - 件名: `[Demo Project - Bug #X] ログインできなくなった`
   - Mailpit を使っている場合は http://localhost:8025 で確認

---

## 7. ID 対応表（メモ用）

セットアップ完了後の参考値（環境ごとに異なるので各自で控える）:

| 種別 | 名称 | ID |
|---|---|---|
| ロール | 質問者 | _____ |
| ロール | 回答者 | _____ |
| ユーザー | questioner | _____ |
| ユーザー | responder | _____ |
| プロジェクト | demo | _____ |

---

## 8. トラブルシューティング

| 症状 | 確認ポイント |
|---|---|
| 「Show user profile」権限が出てこない | hidden_user_profile プラグインが入っていない、または `bundle exec rake redmine:plugins:migrate` 未実行 |
| 質問者で 3 件すべて見えない | チケットの「プライベート」がオン / `質問者` ロールに「チケットの閲覧」権限が無い / `質問者` ロールの「チケットの可視性」が `自分が作成または担当者のチケット` になっている |
| メールが届かない | `管理 → 設定 → メール通知 → テストメール送信` の結果を確認 / `config/configuration.yml` の SMTP 設定 / Spam フォルダ |
| `responder` でも 403 が出る | `回答者` ロールに「Show user profile」権限が付いていない |
| `questioner` でも 200 が返る | 他ロール（特に Manager）に「Show user profile」が残っている |

---

## 9. (Mode C 用) チャットボット連携の追加設定

Mode C (RAG チャットボット) を使う場合、上記までのセットアップに加えて以下を行います。
Mode A / B 運用には不要。

### 9-1. 「+ 新しいチケット」を質問者ロールから非表示にする (推奨)

質問者ロールに `add_issues` 権限を付けた以上、UI から直接「+ 新しいチケット」を
クリックして起票することは原理的に可能。これを抑止して
**「質問者の起票経路はチャットボットのみ」** に近づけるため、View Customize
プラグインで該当 UI を非表示にします。

手順は **[docs/view_customize_setup.md](view_customize_setup.md)** 参照
(プラグインは Dockerfile で導入済み)。

### 9-2. (任意) チャットボット起票識別用カスタムフィールド

UI 経由で直接起票されたチケットを後から識別するため、`Chatbot Session` という
カスタムフィールドを作成し、チャットボット経由の起票時に session ID を自動記録
させると **「チャットボットを通さずに作られたチケット」** が一目で分かるように
なります (監査用)。

1. **管理 → カスタムフィールド** → 右上 **新しいカスタムフィールド**
2. **オブジェクト**: チケット → **次へ**
3. 以下を入力:

   | 項目 | 値 |
   |---|---|
   | 書式 | テキスト |
   | 名称 | `Chatbot Session` |
   | 説明 | チャットボット経由で起票された場合、ここに session ID が記録されます。空ならチャットボット非経由の起票。 |
   | 最小〜最大長 | (空欄) |
   | 正規表現 | (空欄) |
   | デフォルト値 | (空欄) |
   | テキストの書式 | なし |
   | リンク URL | (空欄) |
   | 全プロジェクト用 | ON (推奨) |
   | 必須 | OFF |
   | フィルタとして使用 | ON |
   | 検索対象 | ON (任意) |
   | 表示 | 全ユーザー |

4. **トラッカー**: 起票で使うトラッカー (Support 等) にチェック
5. **作成**
6. 一覧画面に戻り、作成された行の **ID** をメモする (例: `1`)

#### 9-2-1. chatbot 連携設定への反映

`.env` の `CHATBOT_SESSION_CUSTOM_FIELD_ID` に上記の **ID** を設定し、
api コンテナを再起動:

```
CHATBOT_SESSION_CUSTOM_FIELD_ID=1
```

```bash
docker compose -f docker-compose.yml -f compose.api.yml -f compose.chatbot.yml \
    up -d api
```

これ以降、チャットボットからエスカレーションされたチケットには `Chatbot Session`
フィールドに session ID が自動記録されます。UI で起票されたチケットでは空に
なるので、**「`Chatbot Session` 空 + 作成者: 質問者」** のフィルタで
バイパス起票が検出可能です。

> このフィールドは **完全に任意**。ID を `0` のままにしておけば、チャットボット
> は単にこの記録をスキップします (= フィールド未作成でも動作する)。

---

以上で Redmine の Web UI 操作だけでセットアップが完了します。
