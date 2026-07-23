"""Configuration unit tests."""

from pydantic import SecretStr

from lc_asr_pipeline.core.config import Settings


def test_cors_origins_are_normalized() -> None:
    settings = Settings(
        postgres_user="test",
        postgres_password=SecretStr("test"),
        postgres_database="test",
        app_cors_origins="http://localhost:5173, http://127.0.0.1:5173,",
    )

    assert settings.cors_origin_list == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
