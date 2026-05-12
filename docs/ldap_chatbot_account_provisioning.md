# 検討メモ: チャットボット利用時の LDAP 連携アカウント作成

## 目的

チャットボットを初めて使う利用者について、LDAP にアカウントが存在するかを確認し、Redmine 側にユーザーがまだ無ければ自動作成する。

その際、Redmine 上の表示名には LDAP の本名属性をそのまま使わず、所属や利用者区分など別属性から匿名表示用の値を入れる。これにより、LDAP 認証を使いながら、質問者同士に実名が見えにくい状態を保つ。

## 前提

- Redmine 側に LDAP 認証方式が登録されている。
- Redmine REST API が有効化されている。
- API ブリッジは Redmine 管理者相当の API key でユーザー作成できる。
- LDAP 検索用の bind DN / password、base DN、属性名が環境変数で設定できる。
- チャットボット UI は LDAP パスワードをログやセッション履歴に保存しない。

## 想定フロー

```text
chatbot
  -> api: POST /ldap-users/ensure
       1. LDAP で login を検索
       2. 必要なら LDAP bind でパスワードを検証
       3. LDAP 属性から匿名表示名を作る
       4. Redmine に同 login のユーザーが無ければ auth_source_id 付きで作成
       5. Redmine user_id / login / 表示名 / mail を返す
  -> api: POST /memberships
  -> api: POST /tickets
```

既存の `POST /users` はローカル認証ユーザー作成用として残し、LDAP 用には別エンドポイントを追加する方針が安全。

## 追加候補の設定

`api/app/config.py` に追加する候補。

```python
ldap_url: str = "ldap://ldap.example.local:389"
ldap_bind_dn: str = ""
ldap_bind_password: str = ""
ldap_base_dn: str = ""
ldap_login_attr: str = "sAMAccountName"
ldap_mail_attr: str = "mail"

# 本名ではなく匿名表示に使う LDAP 属性
ldap_firstname_attr: str = "department"
ldap_lastname_attr: str = "employeeType"

# Redmine 管理画面で作成した LDAP 認証方式の ID
redmine_ldap_auth_source_id: int = 0

# 既存 Redmine ユーザーの姓名を LDAP 属性で上書きするか
ldap_sync_existing_user_names: bool = False
```

`api/requirements.txt` には LDAP クライアントを追加する。

```txt
ldap3>=2.9,<3.0
```

## LDAP 検索サービス案

`api/app/services/ldap_service.py` を追加する案。

```python
from dataclasses import dataclass

from ldap3 import ALL, Connection, Server
from ldap3.utils.conv import escape_filter_chars

from app.config import settings


class LdapUserNotFound(LookupError):
    pass


class LdapAuthenticationFailed(PermissionError):
    pass


@dataclass
class LdapUser:
    dn: str
    login: str
    mail: str
    firstname: str
    lastname: str


def _attr(entry, name: str, default: str = "") -> str:
    if not name:
        return default
    value = entry.entry_attributes_as_dict.get(name, [])
    if isinstance(value, list):
        return str(value[0]) if value else default
    return str(value or default)


def find_ldap_user(login: str) -> LdapUser:
    server = Server(settings.ldap_url, get_info=ALL)
    conn = Connection(
        server,
        user=settings.ldap_bind_dn or None,
        password=settings.ldap_bind_password or None,
        auto_bind=True,
    )

    safe_login = escape_filter_chars(login)
    search_filter = f"({settings.ldap_login_attr}={safe_login})"
    attrs = {
        settings.ldap_login_attr,
        settings.ldap_mail_attr,
        settings.ldap_firstname_attr,
        settings.ldap_lastname_attr,
    }

    conn.search(
        search_base=settings.ldap_base_dn,
        search_filter=search_filter,
        attributes=[a for a in attrs if a],
        size_limit=1,
    )

    if not conn.entries:
        raise LdapUserNotFound(f"LDAP user not found: {login}")

    entry = conn.entries[0]
    return LdapUser(
        dn=entry.entry_dn,
        login=_attr(entry, settings.ldap_login_attr, login),
        mail=_attr(entry, settings.ldap_mail_attr),
        firstname=_attr(entry, settings.ldap_firstname_attr, "User")[:30],
        lastname=_attr(entry, settings.ldap_lastname_attr, "Anonymous")[:255],
    )


def authenticate_ldap_user(login: str, password: str) -> LdapUser:
    user = find_ldap_user(login)
    server = Server(settings.ldap_url, get_info=ALL)

    if not Connection(server, user=user.dn, password=password, auto_bind=False).bind():
        raise LdapAuthenticationFailed("LDAP authentication failed")

    return user
```

## Redmine ユーザー作成サービス案

`api/app/services/ldap_user_service.py` を追加する案。

```python
from typing import Literal

from pydantic import BaseModel, Field

from app.config import settings
from app.redmine_client import get_redmine
from app.services.ldap_service import authenticate_ldap_user
from app.services.redmine_helpers import find_user_by_login


class EnsureLdapUserRequest(BaseModel):
    login: str = Field(..., min_length=1, max_length=60)
    password: str = Field(..., min_length=1)


class EnsureLdapUserResponse(BaseModel):
    status: Literal["created", "already_exists"]
    user_id: int
    login: str
    firstname: str
    lastname: str
    mail: str


def ensure_ldap_user(req: EnsureLdapUserRequest) -> EnsureLdapUserResponse:
    ldap_user = authenticate_ldap_user(req.login, req.password)
    rm = get_redmine()

    existing = find_user_by_login(rm, ldap_user.login)
    if existing:
        if settings.ldap_sync_existing_user_names:
            existing.firstname = ldap_user.firstname
            existing.lastname = ldap_user.lastname
            existing.mail = ldap_user.mail
            existing.save()

        return EnsureLdapUserResponse(
            status="already_exists",
            user_id=existing.id,
            login=existing.login,
            firstname=getattr(existing, "firstname", ""),
            lastname=getattr(existing, "lastname", ""),
            mail=getattr(existing, "mail", ""),
        )

    create_kwargs = {
        "login": ldap_user.login,
        "firstname": ldap_user.firstname,
        "lastname": ldap_user.lastname,
        "mail": ldap_user.mail,
        "mail_notification": "only_my_events",
    }
    if settings.redmine_ldap_auth_source_id:
        create_kwargs["auth_source_id"] = settings.redmine_ldap_auth_source_id

    new_user = rm.user.create(**create_kwargs)

    return EnsureLdapUserResponse(
        status="created",
        user_id=new_user.id,
        login=new_user.login,
        firstname=ldap_user.firstname,
        lastname=ldap_user.lastname,
        mail=ldap_user.mail,
    )
```

## API ルーター案

`api/app/routers/ldap_users.py` を追加し、`api/app/main.py` で include する。

```python
from fastapi import APIRouter, HTTPException

from app.services.ldap_service import LdapAuthenticationFailed, LdapUserNotFound
from app.services.ldap_user_service import (
    EnsureLdapUserRequest,
    EnsureLdapUserResponse,
    ensure_ldap_user,
)

router = APIRouter(prefix="/ldap-users", tags=["ldap-users"])


@router.post("/ensure", response_model=EnsureLdapUserResponse)
def ensure_ldap_user_endpoint(req: EnsureLdapUserRequest) -> EnsureLdapUserResponse:
    try:
        return ensure_ldap_user(req)
    except LdapAuthenticationFailed as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except LdapUserNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LDAP/Redmine error: {e}") from e
```

## チャットボット側の変更点

- セッション作成前またはエスカレーション前に LDAP login / password を受け取る。
- 受け取った password は `POST /ldap-users/ensure` の呼び出しにだけ使う。
- `ChatSession`、ログ、Redmine チケット本文には password を保存しない。
- `ensure` 成功後は、返却された `login` を使って既存の `POST /memberships` と `POST /tickets` の流れに進む。

## 匿名性の検討事項

LDAP の所属、部署、役職、社員区分なども、組織規模や組み合わせによっては個人特定につながる可能性がある。

そのため、表示名に入れる値は以下のいずれかを検討する。

- 粗い分類値: `部門A`、`営業系`、`技術系` など
- 固定ラベル: `質問者`
- LDAP 属性から生成した安定した疑似名
- Redmine カスタムフィールドにだけ詳細属性を保存し、画面表示名には出さない

本名を避けるだけでなく、「少人数部署 + 役職」のような再識別リスクも避ける必要がある。

## 未決事項

- LDAP パスワードをチャットボット UI に入力させるか、別の SSO / リバースプロキシ認証に寄せるか。
- Redmine の `auth_source_id` を環境変数で固定するか、名前から API 起動時に解決するか。
- 既存 Redmine ユーザーの姓名・メールを LDAP 属性で同期するか。
- LDAP に存在しない利用者を、現行のローカル匿名ユーザー作成にフォールバックさせるか。
- LDAP 属性値をどの程度丸めるか、匿名化ポリシーをどこに置くか。
- テスト用 LDAP サーバーを Docker Compose に含めるか。
