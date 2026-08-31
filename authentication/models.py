"""
Password-reset tokens.

Mirrors `tenancy.models.Invitation`'s token shape rather than inventing a
second one: hashed at rest (`token_hash`), the raw value handed back only
once at issuance for the caller to email out, single use, and short-lived.
See `Invitation`'s docstring for why a fast hash (SHA-256, not a slow
password hasher) is the right choice for a 256-bit `secrets` token looked up
by unique index -- the same reasoning applies unchanged here.

Two things deliberately differ from `Invitation`:

* The default expiry is much shorter (`PASSWORD_RESET_DEFAULT_TTL`, one hour,
  against `Invitation`'s seven days). An invitation is handed out by an admin
  who controls when it is used, so a long window is harmless. A reset link
  sits in the requester's own inbox, is normally used within minutes of being
  requested, and is exactly the kind of credential an attacker with delayed
  inbox access (a shared computer, a compromised mail account, an old
  unread email) benefits from most if it stays valid for a long time -- so
  the window is kept small.
* There is no `revoked_at`. An admin can revoke an invitation nobody has
  used yet, but nobody is positioned to revoke someone else's password-reset
  link -- only the requester holds it, and only they would ever want to.
"""
import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

PASSWORD_RESET_DEFAULT_TTL = timedelta(hours=1)


def _hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


class PasswordResetToken(models.Model):
    """A single-use link proving control of the mailbox behind one account."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_reset_tokens"
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"], name="pwreset_user_idx"),
        ]

    def __str__(self):
        return f"Password reset for {self.user}"

    @classmethod
    def issue(cls, *, user, ttl=PASSWORD_RESET_DEFAULT_TTL):
        """Create a new token and return `(token, raw_token)`.

        The raw token is returned only here, once, at creation -- callers
        must hand it to the outgoing email immediately and never persist it
        themselves; only `token_hash` is ever stored.
        """
        raw_token = secrets.token_urlsafe(32)
        token = cls.objects.create(
            user=user,
            token_hash=_hash_reset_token(raw_token),
            expires_at=timezone.now() + ttl,
        )
        return token, raw_token

    @classmethod
    def for_token(cls, raw_token: str):
        """Resolve a raw token to its PasswordResetToken, or None if unknown."""
        try:
            return cls.objects.select_related("user").get(token_hash=_hash_reset_token(raw_token))
        except cls.DoesNotExist:
            return None

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None
