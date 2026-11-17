"""Minimal session auth for the lab: a token bound to a World account.

Not real security (no passwords; the accounts are fake lab data). Its job is to make "who the
customer is" an *authenticated* fact the web app and the agent can trust, instead of a name the
caller types. Ownership checks and the output guard then key off the logged-in identity.
"""
import secrets


class Auth:
    def __init__(self, world):
        self.world = world
        self._tokens = {}          # token -> account name

    def login(self, name):
        """Return a session token for a known account, or None if there is no such account."""
        if not self.world.account(name):
            return None
        token = secrets.token_urlsafe(16)
        self._tokens[token] = name
        return token

    def identity(self, token):
        """Resolve a token to {'name', 'role'}, or None if the token is unknown."""
        name = self._tokens.get(token)
        acct = self.world.account(name) if name else None
        return {"name": acct["name"], "role": acct["role"]} if acct else None

    def logout(self, token):
        self._tokens.pop(token, None)
