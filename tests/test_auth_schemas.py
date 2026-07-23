"""Initial-password request validation tests."""

import pytest
from pydantic import ValidationError

from lc_asr_pipeline.schemas.auth import InitialPasswordChangeRequest


def test_initial_password_accepts_eight_characters() -> None:
    request = InitialPasswordChangeRequest(new_password="Abcdefg1")
    assert request.new_password == "Abcdefg1"


def test_initial_password_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        InitialPasswordChangeRequest(new_password="Abcdef1")
