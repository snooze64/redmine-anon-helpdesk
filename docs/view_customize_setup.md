# View Customize プラグインの設定 (質問者ロール向け UI 抑止)

[onozaty/redmine-view-customize](https://github.com/onozaty/redmine-view-customize) を使って、
**質問者ロールのユーザーには Redmine UI 経由で直接チケットを起票できないようにする**
ための設定手順。

> Mode C (チャットボット運用) を採用していて、「起票はチャットボット経由のみ」に
> 揃えたい場合に使う。本プラグインは UI を **隠すだけ** で権限的にブロックは
> しないため、URL を直接叩く手段までは塞がない (= 抑止であって強制ではない)。

---

## 1. 背景

Redmine の権限モデルでは「経路 (UI vs API vs チャットボット) によって権限を分ける」
ことができない。チャットボット (Mode C) から質問者になりすまして起票するには
**質問者ロールに `add_issues` 権限が必要** ([docs/manual_setup.md §1-1](manual_setup.md))。
しかし権限を付けると質問者は Redmine UI からも直接「+ 新しいチケット」ボタンで起票
できてしまう。これだとチャットボットの RAG (自己解決の試み) を経由しないルートが
生まれてしまうため、UI 側だけ JS で抑止する。

| 経路 | 質問者 | 回答者 | 管理者 |
|---|---|---|---|
| チャットボット (Mode C) | ✅ 推奨経路 | ✅ | ✅ |
| Redmine UI グローバルの「+ 新しいチケット」 (`/issues` 等) | ❌ §3-1 で非表示 | ❌ §3-1 で非表示 | ❌ §3-1 で非表示 |
| Redmine UI グローバル `/issues/new` を直接 URL 入力 | ❌ §3-2 で案内表示 | ❌ §3-2 で案内表示 | ✅ 通常通り |
| Redmine UI プロジェクト内の「+ 新しいチケット」 | ❌ §3-1 で非表示 | ✅ | ✅ |
| Redmine UI `/projects/<id>/issues/new` を直接 URL 入力 | ❌ §3-2 で案内表示 | ✅ | ✅ |
| Redmine REST API (`POST /issues`) を直接叩く | ⚠️ できる (権限的に止められない) | ✅ | ✅ |

設計意図:
- **グローバル系は全員不可** — 「プロジェクトを選ばずに起票」は運用上の混乱が
  大きい (どこに入ったのか分からないチケットが生まれる)。管理者であっても
  プロジェクトに入ってから起票するフローに統一する
- **プロジェクト内では質問者だけ不可** — 質問者はチャットボット → エスカレーション
  経路に統一し、回答者・管理者は通常通り Redmine UI から起票可
- **REST API 直叩きは防げない** — Redmine の権限モデルがそこを区別できないため。
  バイパス起票は監査用カスタムフィールドで事後検知する (§6)

---

## 2. プラグインインストール

本リポジトリの `Dockerfile` で **既に焼き込み済み** (`/usr/src/redmine/plugins/view_customize`)。
新規にビルドし直したら自動的に入る:

```powershell
docker compose build redmine
docker compose up -d
docker compose exec -T redmine bundle exec rake redmine:plugins:migrate
docker compose restart redmine
```

### 2-1. インストール確認

`管理 → プラグイン` に **View customize plugin** (バージョン表示あり) が表示されれば成功。
表示されなければ `docker compose logs redmine` でプラグイン読込時の例外を確認。

`管理` メニューの一番下に **「表示のカスタマイズ」** が出てくれば設定可能な状態。

### 2-2. プラグイン設定について

§3 の JS は **クライアントサイドで完結する判定** に変更しているため、
View Customize プラグインの「API アクセスキー自動生成」設定は **不要**。
追加のプラグイン設定なしで動作する。

> 過去版では `/users/current.json` を fetch して memberships を見ていたため
> API キー自動生成設定が必要だったが、現行版は `ViewCustomize.context` の
> 同期判定 + 「グローバルページは全員非表示」というルール簡略化で
> ネットワーク呼び出しを廃止している。

---

## 3. カスタマイズ設定の追加

`管理 → 表示のカスタマイズ` → **新しい表示のカスタマイズ**

以下 2 件を登録する (UI ボタン非表示用 + URL 直叩き対策用)。

### 3-1. 「+ 新しいチケット」を非表示にする

| 項目 | 値 |
|---|---|
| パスのパターン | (空欄でも可。全ページ対象) |
| プロジェクトのパターン | (空欄でも可) |
| 種別 | **JavaScript** |
| 挿入位置 | **全ページの末尾** (DOM 構築後に走らせる必要があるため) |
| 有効 | ✅ |
| コメント | `hide-new-issue-link` |

**ポリシー**:

| ページ種別 | 管理者 | 回答者 | 質問者 |
|---|---|---|---|
| グローバルページ (`/issues`, トップ等、`ctx.project` が無いページ) | 非表示 | 非表示 | 非表示 |
| プロジェクトページ (`/projects/<id>/...`) | 表示 | 表示 | 非表示 |

> **狙い**: グローバルページの「+ 新しいチケット」はプロジェクトを選ばずに
> 起票できてしまい、運用上「結局どのプロジェクトに入ったの?」と混乱を生む。
> 全員 (管理者含む) 隠す方が事故が少ない。プロジェクトページでは管理者・
> 回答者は通常通り起票でき、質問者だけがチャットボットに誘導される。

**コード** 欄に以下を貼り付け:

```javascript
// グローバルページでは全員に「+ 新しいチケット」を表示しない。
// プロジェクトページでは「質問者」ロールのみ非表示。
(function () {
  if (!window.ViewCustomize || !ViewCustomize.context) return;

  var ctx = ViewCustomize.context;

  function hide() {
    document
      .querySelectorAll('a[href$="/issues/new"], a[href*="/issues/new?"]')
      .forEach(function (el) {
        el.style.display = 'none';

        // メニュー項目の場合は <li> ごと隠す
        var li = el.closest('li');
        if (li) li.style.display = 'none';

        // contextual 内に他の表示リンクがなければ contextual ごと隠す
        var contextual = el.closest('.contextual');
        if (contextual) {
          var visible = Array.from(contextual.querySelectorAll('a')).filter(function (a) {
            return a.style.display !== 'none';
          });
          if (visible.length === 0) contextual.style.display = 'none';
        }
      });

    // Redmine 6 の "+" メニュー対策
    var newObj = document.querySelector('#new-object');
    if (newObj && newObj.parentElement) {
      var children = newObj.parentElement.querySelectorAll('ul.menu-children li');
      var anyVisible = Array.from(children).some(function (li) {
        return li.style.display !== 'none';
      });

      if (children.length > 0 && !anyVisible) {
        newObj.parentElement.style.display = 'none';
      }
    }
  }

  function hideTwice() {
    hide();
    setTimeout(hide, 500);
  }

  // グローバルページ (ctx.project が無いページ) は、ロールに関係なく全員非表示。
  // 管理者も含めて非表示にしたい場合は、この位置で判定する。
  if (!ctx.project) {
    hideTwice();
    return;
  }

  // ここから下はプロジェクトページ用。
  // 管理者はプロジェクトページでは素通し。
  if (ctx.user && ctx.user.admin) return;

  function checkOnlyQuestioner() {
    var roles = (ctx.project && ctx.project.roles) || [];

    if (roles.length > 0) {
      return Promise.resolve(
        roles.every(function (r) {
          return r.name === '質問者';
        })
      );
    }

    return Promise.resolve(false);
  }

  checkOnlyQuestioner().then(function (yes) {
    if (!yes) return;
    hideTwice();
  });
})();
```

### 3-2. URL 直叩き対策 (`/issues/new` に来たユーザーにチャットボットを案内)

| 項目 | 値 |
|---|---|
| パスのパターン | (空欄でも OK。JS 内で `/issues/new$` の正規表現マッチを行うため、他ページに副作用は出ない) |
| プロジェクトのパターン | (空欄) |
| 種別 | **JavaScript** |
| 挿入位置 | **全ページの末尾** (DOM 構築後に走らせる必要があるため) |
| 有効 | ✅ |
| コメント | `redirect-from-new-issue` |

**ポリシー**:

| ページ | 管理者 | 回答者 | 質問者 |
|---|---|---|---|
| グローバル `/issues/new` | ✅ 通常通り | ❌ 案内表示 | ❌ 案内表示 |
| プロジェクト `/projects/<id>/issues/new` | ✅ 通常通り | ✅ 通常通り | ❌ 案内表示 |

> グローバル `/issues/new` は「プロジェクトを選ばないまま起票」の入口になり、
> 運用上の混乱を生むため、管理者以外は全員チャットボット (またはプロジェクト内
> 起票) に誘導する。プロジェクト内では質問者だけがチャットボットに誘導される。

**コード**:

```javascript
// 質問者ロールのみのユーザーが新規チケット作成画面に直接来た場合、
// チャットボットを案内する。
//
// 挙動:
//   - 管理者:
//       グローバル /issues/new でも、プロジェクト配下 /projects/xxx/issues/new でも素通し
//   - グローバル /issues/new:
//       管理者以外はロールに関係なくチャットボット案内を表示
//   - プロジェクト配下 /projects/xxx/issues/new:
//       「質問者」ロールのみのユーザーだけチャットボット案内を表示
//       それ以外のロールは通常表示
(function () {
  if (!window.ViewCustomize || !ViewCustomize.context) return;

  var ctx = ViewCustomize.context;

  // 管理者はすべて素通し
  if (ctx.user && ctx.user.admin) return;

  // 現在のURLが新規チケット作成画面でなければ何もしない
  // 例:
  //   /issues/new
  //   /projects/sample/issues/new
  var path = window.location.pathname;
  var isNewIssuePage = /\/issues\/new\/?$/.test(path);

  if (!isNewIssuePage) return;

  // チャットボット URL は環境に応じて書き換えてください
  var chatbotUrl = 'http://localhost:8501';

  function showChatbotGuide() {
    var c = document.getElementById('content') || document.body;

    c.innerHTML =
      '<div style="padding:24px;border:2px solid #c44;background:#fee;border-radius:8px;">' +
        '<h2 style="margin:0 0 12px;">📨 質問はチャットボットからお願いします</h2>' +
        '<p>' +
          '質問の起票は <b>チャットボット</b> 経由でお願いしています。' +
          'AI が過去の類似チケットを参照して即時回答を試みます。' +
          'それでも解決しない場合のみ Redmine にエスカレーションされます。' +
        '</p>' +
        '<p>' +
          '<a href="' + chatbotUrl + '" ' +
             'style="display:inline-block;padding:10px 20px;background:#0a7;color:#fff;border-radius:4px;text-decoration:none;font-weight:bold;">' +
            '🤖 チャットボットを開く' +
          '</a>' +
        '</p>' +
      '</div>';
  }

  // グローバル /issues/new の場合
  // ctx.project が無いので、管理者以外はロールに関係なく案内する
  if (!ctx.project) {
    showChatbotGuide();
    return;
  }

  // プロジェクト配下 /projects/xxx/issues/new の場合
  // 「質問者」ロールのみなら案内する
  var roles = ctx.project.roles || [];

  if (roles.length === 0) return;

  var onlyQuestioner = roles.every(function (r) {
    return r.name === '質問者';
  });

  if (!onlyQuestioner) return;

  showChatbotGuide();
})();
```

> - 旧版で必要だった「パスのパターンを `/issues/new$` に絞ること」は、JS 内で
>   `window.location.pathname` を正規表現でチェックするようになったため不要。
>   空欄のままで OK (全ページにロードされるが、対象ページ以外では何もせず終了)。
> - JS 中の `chatbotUrl` はあなたの環境に合わせて書き換えてください
>   (例: `https://chatbot.example.com`)。

---

## 4. 動作確認

### 4-1. 質問者 (`questioner`)

1. ブラウザのプライベートウィンドウ等で `questioner` でログイン
2. プロジェクト Demo の **チケット一覧** を開く → 右上に
   「+ 新しいチケット」が **出ていない** (§3-1)
3. URL バーに `http://localhost:3080/projects/demo/issues/new` を直接入力
   → フォームではなく **「チャットボットからお願いします」案内** が出る (§3-2)
4. グローバルの `/issues` を開く → トップ右上の「+」メニューに
   「新しいチケット」が **出ていない** (§3-1)
5. グローバル `/issues/new` を直接 URL 入力 → **案内が出る** (§3-2)

### 4-2. 回答者 (`responder`)

1. 別ブラウザで `responder` でログイン
2. プロジェクト Demo を開く → **「+ 新しいチケット」が表示される** (§3-1 通り)
3. プロジェクト内の「+ 新しいチケット」をクリック → 通常通り起票画面が開く
4. グローバルの `/issues` を開く → 右上の「+」メニュー /
   「新しいチケット」リンクが **出ていない** (§3-1 / 運用事故抑止のため全員非表示)
5. グローバル `/issues/new` を直接 URL 入力 → **案内が出る** (§3-2 / 管理者以外は同じ扱い)

### 4-3. 管理者 (`admin`)

1. `admin` でログイン
2. プロジェクト Demo → **「+ 新しいチケット」が表示される** (§3-1 通り)
3. プロジェクト内 / グローバル `/issues/new` のどちらに直接アクセスしても
   **通常の起票フォームが表示される** (§3-2 で素通し)
4. ただしグローバル `/issues` 等の「+」メニューは **非表示** (§3-1 / 全員対象)。
   起票するならプロジェクトに入ってから、というワークフローに揃えてある

---

## 5. なぜ完全強制にならないか (制限事項)

- View Customize は **クライアントサイド JS** で実現。ブラウザの DevTools で JS を
  無効化したり、curl で `POST /issues` を叩いたりすれば技術的にバイパス可能
- 完全に強制したいなら Redmine プラグインを自作してサーバサイドで「`X-Redmine-Switch-User`
  ヘッダ無しの POST /issues は質問者ロールから拒否」する判定が必要 (本リポジトリ
  では未実装)
- 実用上の妥協点として、**カジュアル利用** (= UI を素直に使うユーザー) には
  完全に隠せる。技術力のあるバイパスは想定しない、という割り切り

---

## 6. 監査 (バイパス検知の手がかり)

「UI 経由 / API 直叩きで起票されたか」を区別するため、カスタムフィールド
`Chatbot Session` を作成しておくと便利。チャットボット経由の起票時にはこの
フィールドにチャットボット session ID が **自動記録** され、UI 直叩きで作られた
チケットでは空になります。

セットアップ手順は **[docs/manual_setup.md §9-2](manual_setup.md)** を参照。

検出クエリの例:

- プロジェクト: demo
- フィルタ:
  - 作成者: 質問者ロールのユーザー
  - Chatbot Session: 空である
- → 該当チケットは「質問者が UI から直接起票したもの」の候補

実装は完了済み:
- `api/app/services/ticket_service.py`: `chatbot_session_id` 受領 + カスタム
  フィールドへの書込
- `chatbot/app/session/escalate.py` → `chatbot/app/routers/sessions.py`:
  session ID を bridge API に伝搬
- `.env` で `CHATBOT_SESSION_CUSTOM_FIELD_ID` を Redmine 上のフィールド ID に
  設定して有効化 (`0` のままなら無効)

---

## 7. アンインストール

「Mode C を使わない」「UI 制限を外したい」場合:

1. `管理 → 表示のカスタマイズ` で §3-1, §3-2 のエントリを削除 (or 「有効」を OFF)
2. プラグイン自体を外したい場合は `Dockerfile` から `view_customize` の
   `git clone` 行を削除して再ビルド
