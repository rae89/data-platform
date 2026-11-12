import importlib.util
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

spec = importlib.util.spec_from_file_location(
    "cf_access", Path(__file__).parents[1] / "superset" / "cf_access.py"
)
cf_access = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cf_access)

TEAM, AUD = "team.cloudflareaccess.com", "app-aud"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJwks:
    """Stands in for Cloudflare's public keys (PyJWKClient)."""

    def __init__(self, key=KEY, error=None):
        self.key, self.error = key.public_key(), error

    def get_signing_key_from_jwt(self, token):
        if self.error:
            raise self.error
        return self


def token(key=KEY, **overrides):
    claims = {"email": "me@example.com", "aud": AUD, "iss": f"https://{TEAM}", "exp": time.time() + 60}
    return jwt.encode(claims | overrides, key, algorithm="RS256")


def run(environ, jwks=None):
    seen = {}

    def app(env, start_response):
        seen["user"] = env.get("REMOTE_USER")
        return []

    cf_access.CloudflareAccessMiddleware(app, TEAM, AUD, jwks or FakeJwks())(environ, None)
    return seen["user"]


def test_valid_token_signs_in_its_email():
    assert run({"HTTP_CF_ACCESS_JWT_ASSERTION": token()}) == "me@example.com"


@pytest.mark.parametrize(
    "bad",
    [
        token(key=OTHER_KEY),  # not signed by Cloudflare
        token(aud="other-app"),  # another Access app's token
        token(iss="https://evil.cloudflareaccess.com"),
        token(exp=time.time() - 60),  # expired
        token(email=""),
        "not-a-jwt",
    ],
)
def test_invalid_tokens_sign_in_nobody(bad):
    assert run({"HTTP_CF_ACCESS_JWT_ASSERTION": bad}) is None


def test_only_a_verified_token_sets_remote_user():
    # A REMOTE_USER that didn't come from a token (or a faked email header) is dropped.
    environ = {"REMOTE_USER": "admin", "HTTP_CF_ACCESS_AUTHENTICATED_USER_EMAIL": "me@example.com"}
    assert run(environ) is None


def test_unreachable_keys_sign_in_nobody():
    error = jwt.PyJWKClientConnectionError("no network")
    assert run({"HTTP_CF_ACCESS_JWT_ASSERTION": token()}, FakeJwks(error=error)) is None


def test_role_for_listed_admins_only():
    admins = {"me@example.com"}
    assert cf_access.role_for("Me@Example.com", admins) == "Admin"
    assert cf_access.role_for("visitor@example.com", admins) == "Gamma"


def test_jwks_url_is_the_teams_public_keys():
    middleware = cf_access.CloudflareAccessMiddleware(None, TEAM, AUD)
    assert middleware.jwks.uri == f"https://{TEAM}/cdn-cgi/access/certs"
