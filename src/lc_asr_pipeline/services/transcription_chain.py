"""LangChain boundary for provider-neutral ASR execution."""

from langchain_core.runnables import Runnable, RunnableLambda

from lc_asr_pipeline.providers.base import ASRProvider
from lc_asr_pipeline.schemas.transcription import TranscriptionRequest, TranscriptionResult


def build_transcription_chain(
    provider: ASRProvider,
) -> Runnable[TranscriptionRequest, TranscriptionResult]:
    """Wrap an ASR provider as a typed LangChain Runnable."""
    return RunnableLambda(provider.invoke, afunc=provider.ainvoke).with_types(
        input_type=TranscriptionRequest,
        output_type=TranscriptionResult,
    )
