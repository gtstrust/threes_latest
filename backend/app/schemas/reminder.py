from datetime import datetime

from pydantic import BaseModel


class ReminderSentRead(BaseModel):
    """The answer to "remind the field": how many messages the provider accepted.

    Accepted, not delivered — nothing this side of an inbox can promise the
    second. Zero is a real answer rather than a failure: a field of virtual
    players has nobody to write to, and the organiser is better told that than
    left assuming.
    """

    sent: int


class LastReminderRead(BaseModel):
    """When the field was last written to, for the organiser's screen."""

    sent_at: datetime | None
    recipient_count: int | None


class SweepResultRead(BaseModel):
    """What one run of the scheduled sweep did.

    Counts rather than a bare acknowledgement, so a scheduler's logs record what
    happened rather than only that something did.
    """

    events_reminded: int
