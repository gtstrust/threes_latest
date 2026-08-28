"""Generating the short code that stands in for an invitation.

Pure and synchronous, alongside `scoring.py` and `grouping.py` — no session, no
I/O, plain data out — so the one thing that must never quietly produce collisions
or unreadable codes can be tested exhaustively without fixtures.

The code is what an organiser hands out: printed on a sign, encoded in a QR, or
read aloud on a tee. Two consequences shape it. The alphabet drops every glyph
that is ambiguous when read off a screen at arm's length — no `0`/`O`, no
`1`/`I`/`L` — because a code that can't be transcribed is worse than a long one.
And it is deliberately *not* the tournament's id: an id can never be revoked,
while a code can be regenerated the moment a printed link outlives its event.
"""

import secrets

# Crockford's base32 alphabet minus the vowels that make words out of noise.
# 30 symbols, so five characters is ~24 million codes — comfortable against a
# unique constraint and a retry, and short enough to say out loud.
ALPHABET = "23456789BCDFGHJKMNPQRSTVWXYZ"

PREFIX = "THR-"
CODE_LENGTH = 5


def generate_join_code() -> str:
    """A fresh join code, e.g. `THR-8K2QF`.

    Uniqueness is the database's job, not this function's: it draws from
    `secrets` and the caller retries against the unique constraint. Trying to
    guarantee it here would mean a read before every write, and still race.
    """
    body = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    return f"{PREFIX}{body}"


def normalise_join_code(code: str) -> str:
    """The stored form of a code someone typed.

    Codes are stored uppercase, so lookup is a plain comparison rather than a
    functional index — and somebody typing `thr-8k2qf` into a phone still finds
    their event. Surrounding whitespace goes too; it arrives with every paste.
    """
    return code.strip().upper()
