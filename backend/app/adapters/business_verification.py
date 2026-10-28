"""Business registration checks against the National Tax Service (spec 3.11.2, 3.11.13): the interface.

The NTS implementation is in app/adapters/nts_business_verification.py. A check either answers
(the three values match, with the business status, or they do not) or raises
`BusinessVerificationUnavailable`; the caller decides what that means (an `unavailable` application
on submission, `503` on an operator recheck).
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.models import BusinessStatus


class BusinessVerificationUnavailable(Exception):
    """The check could not be made: network error, timeout, quota, or an unexpected response.
    Messages name only the kind of failure, never the values checked or the service key."""


@dataclass(frozen=True)
class BusinessCheck:
    matched: bool
    # The NTS status when matched; None when not matched or when NTS gave no status we know.
    business_status: BusinessStatus | None = None


class BusinessVerifier(Protocol):
    def verify(self, business_registration_number: str, representative_name: str, opening_date: date) -> BusinessCheck:
        """Check that the three values belong together. Raises BusinessVerificationUnavailable."""
        ...
