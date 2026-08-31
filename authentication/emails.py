"""
Shared email-identity helpers.

`auth.User.email` is Django's own field -- we cannot add `unique=True` to it
by editing the model, so uniqueness is enforced with a database-level unique
index created in a migration instead (see
authentication/migrations/0001_email_required_unique.py, which explains why
the index lives there). Every place that sets a User's email -- the register
view, that migration's backfill, and any future admin/management entry point
-- must normalise through `normalize_email` first, so the value it writes is
always exactly what the unique index expects. A check that normalises and an
index that does not is a race waiting to happen.
"""
from django.core.mail import send_mail
from django.core.validators import validate_email

# Mirrors authentication/migrations/0001_email_required_unique.py's
# PLACEHOLDER_DOMAIN. Duplicated rather than imported: that migration is
# historical and must not import application code that can change
# independently of it (see its own docstring), but application code importing
# a literal back out of a migration would create the same kind of coupling in
# the other direction, so the domain is just repeated here instead.
PLACEHOLDER_EMAIL_DOMAIN = "no-email.invalid"


def is_placeholder_email(email: str) -> bool:
    """
    True for the deterministic `user-<id>@no-email.invalid` address the
    email-uniqueness migration assigned to accounts that had no real email.
    There is no mailbox behind it, so nothing -- a password reset included --
    can ever be delivered to it.
    """
    return email.endswith(f"@{PLACEHOLDER_EMAIL_DOMAIN}")


def send_password_reset_email(user, raw_token):
    """
    Send the one and only place the plain reset token is ever emitted.

    There is no frontend route yet to build a clickable link around (the UI
    is step 4 of this change), so the message carries the raw token itself --
    the same "hand back the plaintext once, here, and never persist it"
    contract `tenancy.models.Invitation.issue` uses for invitation links.
    """
    send_mail(
        subject="Reset your Flagward password",
        message=(
            "A password reset was requested for this account.\n\n"
            f"Reset token: {raw_token}\n\n"
            "If you did not request this, you can safely ignore this email."
        ),
        from_email=None,  # falls back to settings.DEFAULT_FROM_EMAIL
        recipient_list=[user.email],
    )


def normalize_email(value):
    """
    Canonicalise an email address for storage and comparison.

    Mailboxes are treated as case-insensitive: `Brian@example.com` and
    `brian@example.com` are the same inbox to a human, so both the local
    part and the domain are lowercased. This is a deliberate simplification
    of RFC 5321, which technically allows a case-sensitive local part --
    but essentially no real mail provider enforces that distinction, and
    treating the two forms as different accounts is how someone ends up
    with two accounts and no way to tell which one is theirs.
    """
    return value.strip().lower()


def validate_normalized_email(value):
    """
    Raise `django.core.exceptions.ValidationError` if `value` (already run
    through `normalize_email`) is not a plausible email address.
    """
    validate_email(value)
