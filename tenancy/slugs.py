"""
Deriving a URL-safe key from a name a human typed.

`Project.key` and `Environment.key` used to be hand-typed, which asked people
to invent a string that resolves nothing: no URL, filter, lookup or SDK path
reads either of them -- everything addresses rows by UUID and the SDK
authenticates with `Environment.api_key`. They survive only in `__str__`,
Django admin search, and their uniqueness constraints, so the server derives
them instead.

`FeatureFlag.key` is deliberately NOT derived here: that one is the literal
string a developer writes in `useFlag('...')`, and generating it would rename
their code.
"""
from __future__ import annotations

from collections.abc import Iterable

from django.db.models import QuerySet
from django.utils.text import slugify

#: Base key for a name that slugifies to nothing.
#:
#: `slugify` strips everything it cannot transliterate, so an all-emoji, an
#: all-punctuation, or (under `ALLOW_UNICODE=False`) an all-CJK name reduces
#: to the empty string -- which no `SlugField` will accept. A fixed, readable
#: word is preferred over a hash of the name: it is deterministic, it stays
#: pronounceable in the admin and in `__str__`, and the collision suffix below
#: already keeps a second unnameable sibling apart (`untitled`, `untitled-2`).
#: A hash would be equally unique and equally unreadable for every such name,
#: which is the wrong trade for a field a human may later rename by hand.
EMPTY_SLUG_FALLBACK = "untitled"

#: How many times a derived key may be re-derived and re-saved after losing a
#: uniqueness race. Two concurrent creates can both read the same slug as
#: free; the database rejects the loser, and the loser is expected to come
#: back with the next free key rather than fail. Bounded, because an
#: unbounded retry against a genuinely broken constraint is an outage.
DERIVED_KEY_MAX_ATTEMPTS = 3


def unique_key(
    *,
    base_name: str,
    queryset: QuerySet,
    field: str = "key",
    max_length: int = 255,
    taken: Iterable[str] = (),
) -> str:
    """
    Return a slug of `base_name` that no row in `queryset` already holds.

    `queryset` carries the uniqueness scope -- projects of one organization,
    environments of one project -- so the caller decides what "already taken"
    means and this helper never has to know.

    Three edges it settles, so that both serializers settle them identically:

    * A name that slugifies to `""` falls back to `EMPTY_SLUG_FALLBACK`.
    * A taken slug gets `-2`, `-3`, ... until one is free. Numbering starts at
      2 because the unsuffixed slug is conceptually the first.
    * `max_length` (255 on both `SlugField`s) is a hard ceiling on the WHOLE
      key: the base is cut back to leave room for the suffix, rather than
      appending past the limit and letting the database truncate or reject it.

    `taken` marks keys as unavailable on top of whatever `queryset` holds. It
    exists for the retry after a uniqueness race: the row that won may not be
    visible to this transaction's snapshot yet, and re-offering the key that
    just lost would only lose again.
    """
    taken = frozenset(taken)
    base = slugify(base_name or "") or EMPTY_SLUG_FALLBACK

    candidate = _fit(base, "", max_length)
    counter = 1
    while candidate in taken or queryset.filter(**{field: candidate}).exists():
        counter += 1
        suffix = f"-{counter}"
        candidate = _fit(base, suffix, max_length)
    return candidate


def _fit(base: str, suffix: str, max_length: int) -> str:
    """
    Truncate `base` so that `base + suffix` fits in `max_length`.

    Cutting mid-slug can land on a separator, so the trailing hyphen goes
    too -- `mobile-app-...` truncated to `mobile-` would produce `mobile--2`.
    """
    room = max(max_length - len(suffix), 0)
    trimmed = base[:room].rstrip("-") or EMPTY_SLUG_FALLBACK[:room]
    return f"{trimmed}{suffix}"
