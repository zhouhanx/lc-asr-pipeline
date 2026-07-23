# Local Model Assets

All local speech-model weights and Hugging Face caches must stay below this directory. Large artifacts are ignored by Git; only this guide and `manifest.json` are tracked.

Expected layout:

```text
model/
├── manifest.json
├── cache/huggingface/
├── downloads/qwen3-asr-1.7b/
├── qwen3-asr-1.7b-8bit/
├── qwen3-forced-aligner-0.6b/
└── pyannote-community-1/
```

Use the native macOS model environment, not Docker, for MLX/Metal inference:

```sh
./scripts/model_bootstrap.sh
conda run -n lc-asr-model python scripts/model_doctor.py
conda run -n lc-asr-model python scripts/download_models.py --artifact qwen
./scripts/model_service.sh start
./scripts/model_service.sh status
./scripts/model_service.sh logs
```

Before downloading pyannote Community-1, accept its Hugging Face conditions and place a read-only `PYANNOTE_AUTH_TOKEN` in `.env`. Never commit model files, tokens, interview audio, or transcripts.

The repository-owned service binds to `127.0.0.1:8765` by default and refuses to start until `MLX_ASR_API_KEY` is configured in `.env`. It exposes authenticated OpenAI-compatible transcription, timestamps, and optional diarization. Model loading and inference remain on one dedicated thread to satisfy MLX Metal stream affinity; do not replace it with the upstream `serve` command without rerunning the HTTP regression test.

The local Community-1 artifact is available after its Hugging Face terms are accepted. The service only advertises diarization when `config.yaml` and binary weights pass its completeness check; otherwise ASR and timestamps remain available while diarization requests return `503`.

After accepting the terms and configuring `PYANNOTE_AUTH_TOKEN`, run:

```sh
conda run -n lc-asr-model python scripts/download_models.py --artifact pyannote
./scripts/create_diarization_fixture.sh
conda run -n lc-asr-model python scripts/diarization_smoke.py
```

To test the authenticated HTTP/LangChain path without printing transcript content, run:

```sh
conda run -n lc-asr-pipeline python scripts/smoke_transcribe.py \
  data/fixtures/two-speaker-zh.wav --diarize \
  --output data/test_results/diarization-fixture.json
```
