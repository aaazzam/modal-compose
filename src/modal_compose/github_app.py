from __future__ import annotations

import time

import jwt
import requests

from .errors import GitHubAppNotInstalledError

_JWT_CLOCK_SKEW_SECONDS = 60
_JWT_TTL_SECONDS = 540


def _app_jwt(app_id: str, private_key: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {"iat": now - _JWT_CLOCK_SKEW_SECONDS, "exp": now + _JWT_TTL_SECONDS, "iss": app_id},
        private_key,
        algorithm="RS256",
    )


def mint_installation_token(
    app_id: str, private_key: str, account: str, repo: str | None = None
) -> str:
    headers = {
        "Authorization": f"Bearer {_app_jwt(app_id, private_key)}",
        "Accept": "application/vnd.github+json",
    }

    resp = requests.get("https://api.github.com/app/installations", headers=headers)
    resp.raise_for_status()
    installation = next(
        (i for i in resp.json() if i["account"]["login"] == account), None
    )
    if installation is None:
        raise GitHubAppNotInstalledError(
            f"GitHub App is not installed on account {account!r}"
        )

    token_resp = requests.post(
        f"https://api.github.com/app/installations/{installation['id']}/access_tokens",
        headers=headers,
        json={"repositories": [repo]} if repo else None,
    )
    token_resp.raise_for_status()
    return token_resp.json()["token"]


if __name__ == "__main__":
    import os
    import sys

    print(
        mint_installation_token(
            app_id=os.environ["GITHUB_APP_ID"],
            private_key=os.environ["GITHUB_APP_PRIVATE_KEY"],
            account=sys.argv[1],
            repo=sys.argv[2] if len(sys.argv) > 2 else None,
        )
    )
