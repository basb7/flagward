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
from django.core.validators import validate_email


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
