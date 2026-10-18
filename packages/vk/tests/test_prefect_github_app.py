"""Tests for prefect_flows.github_app: App JWT signing and installation token minting."""

import base64
import json

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from prefect_flows.github_app import AppToken, app_jwt, installation_token


@pytest.fixture(scope="module")
def key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def pem(key: rsa.RSAPrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _b64decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def test_app_jwt_claims_and_signature(key: rsa.RSAPrivateKey, pem: str) -> None:
    token = app_jwt("123", pem, now=1_000_000)

    h, p, s = token.split(".")
    assert json.loads(_b64decode(h)) == {"alg": "RS256", "typ": "JWT"}
    assert json.loads(_b64decode(p)) == {"iat": 999_940, "exp": 1_000_540, "iss": "123"}
    key.public_key().verify(_b64decode(s), f"{h}.{p}".encode(), padding.PKCS1v15(), hashes.SHA256())


def test_installation_token_calls_github(pem: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        route = (request.method, request.url.path)
        if route == ("GET", "/app"):
            return httpx.Response(200, json={"slug": "vk-factory"})
        if route == ("GET", "/repos/sivadotblog/vishwakarma/installation"):
            return httpx.Response(200, json={"id": 7})
        if route == ("POST", "/app/installations/7/access_tokens"):
            return httpx.Response(201, json={"token": "ghs_x"})
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = installation_token("123", pem, "sivadotblog/vishwakarma", client=client)

    assert result == AppToken(token="ghs_x", bot_login="vk-factory[bot]")
    assert len(seen) == 3
    for request in seen:
        assert request.headers["Authorization"].startswith("Bearer ")
        assert request.headers["Accept"] == "application/vnd.github+json"
        assert request.headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert len({r.headers["Authorization"] for r in seen}) == 1
    assert seen[0].headers["Authorization"].count(".") == 2


def test_installation_token_raises_on_http_error(pem: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/app":
            return httpx.Response(200, json={"slug": "vk-factory"})
        return httpx.Response(404, json={"message": "Not Found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        installation_token("123", pem, "sivadotblog/vishwakarma", client=client)
