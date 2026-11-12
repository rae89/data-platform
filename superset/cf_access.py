"""Sign in to Superset with Cloudflare Access instead of Superset's own login page.

Cloudflare Access (infra/public.tf) adds a signed token, `Cf-Access-Jwt-Assertion`, to
every request it lets through. The middleware checks that token against the team's
public keys and passes its email to Superset as REMOTE_USER, which the AUTH_REMOTE_USER
login in superset_config.py signs in. Only the signed token counts: the plain
`Cf-Access-Authenticated-User-Email` header can be faked by anyone who reaches Superset
without going through Cloudflare (SSM port forwarding, Tailscale).
"""

import jwt


class CloudflareAccessMiddleware:
    """WSGI middleware: REMOTE_USER is the email of a valid Access token, or unset."""

    def __init__(self, app, team_domain: str, audience: str, jwks=None):
        self.app = app
        self.issuer = f"https://{team_domain}"
        self.audience = audience
        self.jwks = jwks or jwt.PyJWKClient(f"{self.issuer}/cdn-cgi/access/certs")

    def __call__(self, environ, start_response):
        environ.pop("REMOTE_USER", None)  # only a verified token may set it
        email = self.verified_email(environ.get("HTTP_CF_ACCESS_JWT_ASSERTION"))
        if email:
            environ["REMOTE_USER"] = email
        return self.app(environ, start_response)

    def verified_email(self, token: str | None) -> str | None:
        if not token:
            return None
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, key, algorithms=["RS256"], audience=self.audience, issuer=self.issuer
            )
        except jwt.PyJWTError:  # bad signature, expired, another app's token, keys unreachable
            return None
        return claims.get("email") or None


def role_for(email: str, admin_emails: set[str]) -> str:
    """Admin for listed emails; everyone else gets Superset's read-only Gamma role."""
    return "Admin" if email.lower() in admin_emails else "Gamma"
