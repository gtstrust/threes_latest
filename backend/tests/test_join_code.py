"""The join code generator — pure, so exhaustively checkable without fixtures.

What matters about a code is that it survives being read off a screen and typed
into a phone, and that two events never share one. The first is this module's
job; the second is the unique constraint's, exercised in test_join.py.
"""

import re

from app.services.join_code import (
    ALPHABET,
    CODE_LENGTH,
    JOIN_PREFIX,
    REFERRAL_PREFIX,
    generate_join_code,
    generate_referral_code,
    normalise_code,
)

# Glyphs that are the same shape at arm's length in a low-contrast font. A code
# containing one is a code somebody mistypes on a tee.
AMBIGUOUS = set("O0I1L")


def test_the_alphabet_has_no_ambiguous_glyphs():
    assert AMBIGUOUS.isdisjoint(set(ALPHABET))


def test_a_code_has_the_advertised_shape():
    assert re.fullmatch(
        rf"{re.escape(JOIN_PREFIX)}[{ALPHABET}]{{{CODE_LENGTH}}}", generate_join_code()
    )


def test_codes_differ():
    """Not a uniqueness proof — the constraint is that — but a wired-up check."""
    assert len({generate_join_code() for _ in range(200)}) > 190


def test_a_typed_code_normalises_to_its_stored_form():
    # Somebody reading a code off a sign types it lowercase, and a paste brings
    # whitespace with it. Both have to find the event.
    assert normalise_code("  thr-8k2qf ") == "THR-8K2QF"
    assert normalise_code("THR-8K2QF") == "THR-8K2QF"


def test_a_referral_code_is_the_same_shape_with_its_own_prefix():
    """One alphabet, because both kinds get read aloud and retyped."""
    code = generate_referral_code()

    assert re.fullmatch(rf"{re.escape(REFERRAL_PREFIX)}[{ALPHABET}]{{{CODE_LENGTH}}}", code)


def test_the_two_kinds_cannot_be_mistaken_for_each_other():
    """A code pasted into the wrong box should fail loudly, not resolve to
    something unrelated."""
    assert not generate_referral_code().startswith(JOIN_PREFIX)
    assert not generate_join_code().startswith(REFERRAL_PREFIX)
