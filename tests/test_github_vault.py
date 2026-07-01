from __future__ import annotations

import pytest

from modal_compose import _github_vault

pytestmark = pytest.mark.unit


class TestVault:
    def test_token_endpoint_mints_using_env_and_returns_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_APP_ID", "123")
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "fake-key")
        monkeypatch.setenv("GITHUB_APP_ACCOUNT", "acme")
        monkeypatch.setenv("GITHUB_APP_REPO", "web")

        calls: list[dict[str, str | None]] = []

        def fake_mint(
            app_id: str, private_key: str, account: str, repo: str | None = None
        ) -> str:
            calls.append(
                {
                    "app_id": app_id,
                    "private_key": private_key,
                    "account": account,
                    "repo": repo,
                }
            )
            return "ghs_minted"

        monkeypatch.setattr(_github_vault, "mint_installation_token", fake_mint)

        assert _github_vault.token() == {"token": "ghs_minted"}
        assert calls == [
            {
                "app_id": "123",
                "private_key": "fake-key",
                "account": "acme",
                "repo": "web",
            }
        ]
