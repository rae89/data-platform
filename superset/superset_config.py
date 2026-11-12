# Superset settings for the data platform (loaded via SUPERSET_CONFIG_PATH).
# SUPERSET_SECRET_KEY comes from the environment; Superset reads it itself.
# Metadata (users, charts, dashboards) lives in SQLite under /app/superset_home.

import os

ROW_LIMIT = 10_000

# Trust X-Forwarded-Proto/Host from cloudflared (infra/public.tf), so redirects stay on
# https and the public hostname. Superset is only reachable through it or localhost.
ENABLE_PROXY_FIX = True

# Behind Cloudflare Access, sign in with its token instead of Superset's login page
# (cf_access.py). On only when both are set, i.e. on the public server; locally the
# `admin` password login stays.
CF_ACCESS_TEAM_DOMAIN = os.environ.get("CF_ACCESS_TEAM_DOMAIN", "")
CF_ACCESS_AUD = os.environ.get("CF_ACCESS_AUD", "")

if CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD:
    from cf_access import CloudflareAccessMiddleware, role_for
    from flask_appbuilder.security.manager import AUTH_REMOTE_USER
    from superset.security import SupersetSecurityManager

    ADMIN_EMAILS = {
        e.strip().lower() for e in os.environ.get("SUPERSET_ADMIN_EMAILS", "").split(",") if e.strip()
    }

    class CloudflareAccessSecurityManager(SupersetSecurityManager):
        # Superset 6 always installs its own login and sign-up pages unless told not to;
        # without them, Flask-AppBuilder's REMOTE_USER login view handles /login/.
        register_superset_auth_view = False
        register_superset_registeruser_view = False

        def auth_user_remote_user(self, username):
            # Creates the user on first visit, then keeps role and email in sync with
            # SUPERSET_ADMIN_EMAILS (removing someone from it demotes them next login).
            user = super().auth_user_remote_user(username)
            role = self.find_role(role_for(username, ADMIN_EMAILS))
            if user and (user.roles != [role] or user.email != username):
                user.roles = [role]
                user.email = username
                self.update_user(user)
            return user

    AUTH_TYPE = AUTH_REMOTE_USER
    AUTH_USER_REGISTRATION = True
    AUTH_USER_REGISTRATION_ROLE = "Gamma"
    # Superset's page setup reads this whenever registration is on; there's no sign-up
    # form here (users come from the token), so no CAPTCHA.
    RECAPTCHA_PUBLIC_KEY = ""
    CUSTOM_SECURITY_MANAGER = CloudflareAccessSecurityManager
    ADDITIONAL_MIDDLEWARE = [
        lambda app: CloudflareAccessMiddleware(app, CF_ACCESS_TEAM_DOMAIN, CF_ACCESS_AUD)
    ]
