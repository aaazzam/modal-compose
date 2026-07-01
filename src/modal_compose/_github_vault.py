from __future__ import annotations

import os

from fastapi import FastAPI

from .github_app import mint_installation_token

app = FastAPI()


@app.post("/token")
def token() -> dict[str, str]:
    return {
        "token": mint_installation_token(
            app_id=os.environ["GITHUB_APP_ID"],
            private_key=os.environ["GITHUB_APP_PRIVATE_KEY"],
            account=os.environ["GITHUB_APP_ACCOUNT"],
            repo=os.environ.get("GITHUB_APP_REPO"),
        )
    }
