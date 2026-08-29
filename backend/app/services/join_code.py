"""Generating the short codes people pass to each other.

Pure and synchronous, alongside `scoring.py` and `grouping.py` — no session, no
I/O, plain data out — so the one thing that must never quietly produce collisions
or unreadable codes can be tested exhaustively without fixtures.

Two kinds today, one shape: a **join code** (`THR-…`) standing in for an
invitation to an event, and a **referral code** (`MATE-…`) standing in for the
player who brought somebody to the platform.

The alphabet drops every glyph that is ambiguous when read off a screen at arm's
length — no `0`/`O`, no `1`/`I`/`L` — because a code that can't be transcribed is
worse than a long one. Both kinds get read aloud, printed and retyped, so both
want that. The prefix is the only difference, and it exists so a code pasted into
the wrong box fails loudly instead of resolving to something unrelated.

A code is also deliberately *not* an id. An id can never be revoked, while a code
can be regenerated the moment a printed link outlives its event.
"""

import secrets

# Crockford's base32 alphabet minus the vowels that make words out of noise.
# 30 symbols, so five characters is ~24 million codes — comfortable against a
# unique constraint and a retry, and short enough to say out loud.
ALPHABET = "23456789BCDFGHJKMNPQRSTVWXYZ"

JOIN_PREFIX = "THR-"
REFERRAL_PREFIX = "MATE-"
CODE_LENGTH = 5

# The name migration 0010 and the join-code call sites already use.
PREFIX = JOIN_PREFIX


def generate_code(prefix: str) -> str:
    """A fresh code with the given prefix, e.g. `THR-8K2QF`.

    Uniqueness is the database's job, not this function's: it draws from
    `secrets` and the caller retries against the unique constraint. Trying to
    guarantee it here would mean a read before every write, and still race.
    """
    body = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    return f"{prefix}{body}"


def generate_join_code() -> str:
    """An invitation to an event."""
    return generate_code(JOIN_PREFIX)


def generate_referral_code() -> str:
    """A player's own code, for bringing somebody to the platform."""
    return generate_code(REFERRAL_PREFIX)


def normalise_code(code: str) -> str:
    """The stored form of a code someone typed.

    Codes are stored uppercase, so lookup is a plain comparison rather than a
    functional index — and somebody typing `thr-8k2qf` into a phone still finds
    their event. Surrounding whitespace goes too; it arrives with every paste.
    """
    return code.strip().upper()


# The name the join-code call sites already use. One implementation: what counts
# as "the same code" cannot differ between the two kinds without one of them
# quietly failing to match what somebody typed.
normalise_join_code = normalise_code
