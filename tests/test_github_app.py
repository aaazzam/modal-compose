from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from modal_compose import github_app

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


class FakeResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> object:
        return self._payload


class TestMintInstallationToken:
    def test_mints_a_token_for_the_matching_account(
        self, monkeypatch: pytest.MonkeyPatch, private_key_pem: str
    ) -> None:
        calls: list[tuple[str, str]] = []
        posted_json: list[object] = []

        def fake_get(url: str, headers: dict[str, str]) -> FakeResponse:
            calls.append(("GET", url))
            return FakeResponse(
                [
                    {"id": 1, "account": {"login": "other"}},
                    {"id": 2, "account": {"login": "acme"}},
                ]
            )

        def fake_post(
            url: str, headers: dict[str, str], json: object = None
        ) -> FakeResponse:
            calls.append(("POST", url))
            posted_json.append(json)
            return FakeResponse({"token": "ghs_abc123"})

        monkeypatch.setattr(github_app.requests, "get", fake_get)
        monkeypatch.setattr(github_app.requests, "post", fake_post)

        token = github_app.mint_installation_token(
            app_id="123", private_key=private_key_pem, account="acme"
        )

        assert token == "ghs_abc123"
        assert calls == [
            ("GET", "https://api.github.com/app/installations"),
            ("POST", "https://api.github.com/app/installations/2/access_tokens"),
        ]
        assert posted_json == [None]

    def test_scopes_the_token_to_one_repo_when_given(
        self, monkeypatch: pytest.MonkeyPatch, private_key_pem: str
    ) -> None:
        posted_json: list[object] = []

        monkeypatch.setattr(
            github_app.requests,
            "get",
            lambda url, headers: FakeResponse(
                [{"id": 2, "account": {"login": "acme"}}]
            ),
        )

        def fake_post(
            url: str, headers: dict[str, str], json: object = None
        ) -> FakeResponse:
            posted_json.append(json)
            return FakeResponse({"token": "ghs_scoped"})

        monkeypatch.setattr(github_app.requests, "post", fake_post)

        token = github_app.mint_installation_token(
            app_id="123", private_key=private_key_pem, account="acme", repo="web"
        )

        assert token == "ghs_scoped"
        assert posted_json == [{"repositories": ["web"]}]

    def test_raises_when_app_is_not_installed_on_the_account(
        self, monkeypatch: pytest.MonkeyPatch, private_key_pem: str
    ) -> None:
        monkeypatch.setattr(
            github_app.requests,
            "get",
            lambda url, headers: FakeResponse(
                [{"id": 1, "account": {"login": "other"}}]
            ),
        )

        with pytest.raises(LookupError, match="acme"):
            github_app.mint_installation_token(
                app_id="123", private_key=private_key_pem, account="acme"
            )
