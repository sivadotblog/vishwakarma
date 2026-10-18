"""Mint a GitHub App installation token with an App JWT (stdlib, httpx and cryptography only)."""

import base64
import json
import time
from dataclasses import dataclass

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

API = "https://api.github.com"
API_VERSION = "2022-11-28"
TIMEOUT = 30


@dataclass(frozen=True)
class AppToken:
    token: str
    bot_login: str


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _segment(obj: dict[str, object]) -> str:
    return _b64url(json.dumps(obj, separators=(",", ":")).encode())


def app_jwt(app_id: str, private_key_pem: str, now: float | None = None) -> str:
    """Sign a short-lived RS256 JWT for the App (iat backdated 60s for clock skew)."""
    issued = int(time.time() if now is None else now)
    header = _segment({"alg": "RS256", "typ": "JWT"})
    payload = _segment({"iat": issued - 60, "exp": issued + 540, "iss": app_id})
    key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("GitHub App private key must be an RSA key")
    signature = key.sign(f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64url(signature)}"


def _mint(client: httpx.Client, jwt: str, repo: str) -> AppToken:
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }
    app = client.get(f"{API}/app", headers=headers)
    app.raise_for_status()
    installation = client.get(f"{API}/repos/{repo}/installation", headers=headers)
    installation.raise_for_status()
    minted = client.post(
        f"{API}/app/installations/{installation.json()['id']}/access_tokens", headers=headers
    )
    minted.raise_for_status()
    return AppToken(token=minted.json()["token"], bot_login=f"{app.json()['slug']}[bot]")


def installation_token(
    app_id: str, private_key_pem: str, repo: str, client: httpx.Client | None = None
) -> AppToken:
    """Exchange the App JWT for an installation token on `repo` plus the App's bot login."""
    jwt = app_jwt(app_id, private_key_pem)
    if client is not None:
        return _mint(client, jwt, repo)
    with httpx.Client(timeout=TIMEOUT) as own:
        return _mint(own, jwt, repo)
