"""Run a disposable PostgreSQL → worker → native model service smoke test."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from lc_asr_pipeline.core.config import get_settings
from lc_asr_pipeline.db.pool import Database
from lc_asr_pipeline.services.secrets import resolve_secret_reference
from lc_asr_pipeline.worker import run_worker


async def seed(
    database: Database,
    audio_path: Path,
    provider_type: str,
    base_url: str,
    model_name: str,
    api_key_env: str,
    *,
    diarize: bool,
) -> tuple[str, str]:
    suffix = uuid4().hex[:12]
    tenant_slug = f"model-e2e-{suffix}"
    normalized_email = f"model-e2e-{suffix}@example.invalid"
    capabilities = ["transcription", "timestamps"]
    if diarize:
        capabilities.append("diarization")
    async with database.connection() as connection:
        tenant = await (
            await connection.execute(
                "INSERT INTO tenants (slug, name) VALUES (%s, 'Model E2E') RETURNING id",
                (tenant_slug,),
            )
        ).fetchone()
        user = await (
            await connection.execute(
                """
                INSERT INTO users (email, normalized_email, display_name, password_hash)
                VALUES (%s, %s, 'Model E2E', 'not-used') RETURNING id
                """,
                (normalized_email, normalized_email),
            )
        ).fetchone()
        assert tenant is not None and user is not None
        provider = await (
            await connection.execute(
                """
                INSERT INTO model_providers (
                    tenant_id, name, provider_type, base_url, model_name,
                    api_key_env, capabilities, is_default
                ) VALUES (%s, 'E2E Provider', %s, %s, %s, %s, %s, true)
                RETURNING id
                """,
                (
                    tenant["id"],
                    provider_type,
                    base_url,
                    model_name,
                    api_key_env,
                    Jsonb(capabilities),
                ),
            )
        ).fetchone()
        batch = await (
            await connection.execute(
                """
                INSERT INTO upload_batches (
                    tenant_id, created_by, name, total_bytes, received_bytes,
                    file_count, status
                ) VALUES (%s, %s, 'Model E2E', %s, %s, 1, 'ready')
                RETURNING id
                """,
                (tenant["id"], user["id"], audio_path.stat().st_size, audio_path.stat().st_size),
            )
        ).fetchone()
        assert provider is not None and batch is not None
        uploaded = await (
            await connection.execute(
                """
                INSERT INTO uploaded_files (
                    batch_id, tenant_id, relative_path, original_name, size_bytes,
                    chunk_size, expected_chunks, received_chunks, storage_path, status
                ) VALUES (%s, %s, 'fixture.wav', 'fixture.wav', %s,
                    8388608, 1, 1, %s, 'ready') RETURNING id
                """,
                (batch["id"], tenant["id"], audio_path.stat().st_size, str(audio_path)),
            )
        ).fetchone()
        assert uploaded is not None
        await connection.execute(
            """
            INSERT INTO transcription_jobs (
                tenant_id, created_by, uploaded_file_id, provider_id,
                provider_type_snapshot, base_url_snapshot, model_name_snapshot,
                api_key_env_snapshot, capabilities_snapshot, language, diarize
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Chinese', %s)
            """,
            (
                tenant["id"],
                user["id"],
                uploaded["id"],
                provider["id"],
                provider_type,
                base_url,
                model_name,
                api_key_env,
                Jsonb(capabilities),
                diarize,
            ),
        )
    return tenant_slug, normalized_email


async def verify(
    database: Database,
    tenant_slug: str,
    normalized_email: str,
    expected_text: str | None,
    *,
    diarize: bool,
) -> None:
    async with database.connection() as connection:
        row = await (
            await connection.execute(
                """
                SELECT j.status, j.error_code, j.error_message, t.text,
                       (SELECT count(*) FROM transcript_segments s
                        WHERE s.transcript_id = t.id) AS segment_count,
                       (SELECT count(DISTINCT s.speaker) FROM transcript_segments s
                        WHERE s.transcript_id = t.id AND s.speaker IS NOT NULL) AS speaker_count
                FROM transcription_jobs j
                JOIN tenants tenant ON tenant.id = j.tenant_id
                LEFT JOIN transcripts t ON t.job_id = j.id
                WHERE tenant.slug = %s
                """,
                (tenant_slug,),
            )
        ).fetchone()
        if row is None or row["status"] != "completed":
            state = "missing" if row is None else str(row["status"])
            code = "none" if row is None else str(row["error_code"])
            raise RuntimeError(f"E2E transcription job did not complete: {state}/{code}")
        if int(str(row["segment_count"])) < 1:
            raise RuntimeError("E2E transcription produced no timestamp segments")
        if diarize and int(str(row["speaker_count"])) < 1:
            raise RuntimeError("E2E diarization produced no speaker attribution")
        normalized_result = str(row["text"]).replace("。", "，")
        normalized_expected = expected_text.replace("。", "，") if expected_text else None
        if normalized_expected and normalized_result != normalized_expected:
            raise RuntimeError("E2E transcript did not match expected text")
        print(
            f"status=completed segments={row['segment_count']} "
            f"speakers={row['speaker_count']}"
        )


async def cleanup(database: Database, tenant_slug: str, normalized_email: str) -> None:
    async with database.connection() as connection:
        await connection.execute("DELETE FROM tenants WHERE slug = %s", (tenant_slug,))
        await connection.execute(
            "DELETE FROM users WHERE normalized_email = %s",
            (normalized_email,),
        )


async def run(
    audio_path: Path,
    port: int,
    expected_text: str | None,
    *,
    diarize: bool,
    provider_type: str,
) -> None:
    if provider_type == "stepfun":
        base_url = "https://api.stepfun.com/v1"
        model_name = "stepaudio-2.5-asr"
        api_key_env = "stepfun_api_key"
    else:
        base_url = f"http://127.0.0.1:{port}"
        model_name = "qwen3-asr-1.7b-mlx-8bit"
        api_key_env = "MLX_ASR_E2E_KEY"
    if not resolve_secret_reference(api_key_env):
        raise RuntimeError(f"{api_key_env} is required")
    if provider_type == "stepfun" and diarize:
        raise RuntimeError("StepFun SSE E2E does not support diarization")
    database = Database(get_settings())
    await database.open()
    try:
        tenant_slug, normalized_email = await seed(
            database,
            audio_path,
            provider_type,
            base_url,
            model_name,
            api_key_env,
            diarize=diarize,
        )
        try:
            await run_worker(once=True, poll_seconds=0)
            await verify(
                database,
                tenant_slug,
                normalized_email,
                expected_text,
                diarize=diarize,
            )
        finally:
            await cleanup(database, tenant_slug, normalized_email)
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--expected-text")
    parser.add_argument("--diarize", action="store_true")
    parser.add_argument(
        "--provider",
        choices=("local", "stepfun"),
        default="local",
    )
    arguments = parser.parse_args()
    asyncio.run(
        run(
            arguments.audio.resolve(),
            arguments.port,
            arguments.expected_text,
            diarize=arguments.diarize,
            provider_type=arguments.provider,
        )
    )


if __name__ == "__main__":
    main()
