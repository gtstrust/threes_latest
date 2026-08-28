"""The join code generator — pure, so exhaustively checkable without fixtures.

What matters about a code is that it survives being read off a screen and typed
into a phone, and that two events never share one. The first is this module's
job; the second is the unique constraint's, exercised in test_join.py.
"""

import re

from app.services.join_code import (
    ALPHABET,
    CODE_LENGTH,
    PREFIX,
    generate_join_code,
    normalise_join_code,
)

# Glyphs that are the same shape at arm's length in a low-contrast font. A code
# containing one is a code somebody mistypes on a tee.
AMBIGUOUS = set("O0I1L")


def test_the_alphabet_has_no_ambiguous_glyphs():
    assert AMBIGUOUS.isdisjoint(set(ALPHABET))


def test_a_code_has_the_advertised_shape():
    assert re.fullmatch(rf"{re.escape(PREFIX)}[{ALPHABET}]{{{CODE_LENGTH}}}", generate_join_code())


def test_codes_differ():
    """Not a uniqueness proof — the constraint is that — but a wired-up check."""
    assert len({generate_join_code() for _ in range(200)}) > 190


def test_a_typed_code_normalises_to_its_stored_form():
    # Somebody reading a code off a sign types it lowercase, and a paste brings
    # whitespace with it. Both have to find the event.
    assert normalise_join_code("  thr-8k2qf ") == "THR-8K2QF"
    assert normalise_join_code("THR-8K2QF") == "THR-8K2QF"
