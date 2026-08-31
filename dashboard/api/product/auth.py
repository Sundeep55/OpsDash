"""How the product API authenticates, which is not how the portal does.

THE PROBLEM THIS SOLVES
-----------------------
Everything used to authenticate with the browser session. That meant a tab
logged into the dashboard was, implicitly, a live credential for every endpoint
-- Swagger's "Try it out" worked because the page sent the operator's cookie,
and so would anything else running in that browser.

For the SPA's own endpoints that is unavoidable and correct: it *is* the browser,
and it has no other credential to offer.

For this half it is wrong. These endpoints exist for other teams' scripts and
scrapers, and a machine-facing API should require a machine credential that was
deliberately issued, can be listed, and can be revoked on its own -- not a side
effect of somebody being signed in somewhere.

WHAT CHANGED
------------
    /api/v2/<internal>    session only   -- the SPA, and nothing else
    /api/v2/platform/…    token only     -- and the other five product prefixes
    /api/v2/finops/…
    /api/v2/devex/…
    /api/v2/security/…
    /api/v2/stack/…
    /api/v2/network/…

A signed-in browser can no longer read the product endpoints by virtue of being
signed in. It has to present a token, which means someone had to issue one.

Basic authentication was dropped at the same time. It sends a reusable password
on every request and cannot be revoked without changing that password, which is
strictly worse than a token that can be deleted on its own.

    python manage.py apitoken alice --create      # issue
    python manage.py apitoken --list              # who holds one
    python manage.py apitoken alice --revoke      # take it away

    curl -H "Authorization: Token <value>" https://…/api/v2/finops/quotas/
"""
from rest_framework.authentication import TokenAuthentication


class ProductApiAuthMixin:
    """Token only. Deliberately overrides the project-wide default.

    Listed on every product view rather than inferred from the URL prefix:
    DRF resolves authentication per view, so a view added to this package
    without the mixin would silently fall back to the session default. Being
    explicit means the omission is visible in the file rather than in a
    behaviour nobody notices.
    """
    authentication_classes = [TokenAuthentication]
