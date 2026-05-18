# Atlas Cloud Provider Review

## Scope

Integrated Atlas Cloud into the `5.RAG` provider abstraction with the smallest
possible surface change, keeping the existing OpenAI-compatible design.

## Changed Files

- `5.RAG/src/llm_provider.py`
  - Added the `atlas_cloud` preset.
  - Added `ATLAS_CLOUD_MODEL` support for optional model override.
  - Added `chat_completion_stream()` for streaming validation.
- `5.RAG/tests/test_llm_provider.py`
  - Added Atlas Cloud unit coverage for preset resolution, config building,
    and streaming behavior.
  - Isolated auto-detect tests so local Atlas env vars do not affect MiniMax
    and OpenAI assertions.
- `5.RAG/tests/test_integration.py`
  - Added live Atlas Cloud tests for standard completion, streaming, grounded
    Q&A, and summarization.
- `5.RAG/.env.example`
  - Documented `ATLAS_CLOUD_API_KEY` and `ATLAS_CLOUD_MODEL`.
- `5.RAG/README.md`
  - Added Atlas Cloud setup instructions and official project-tracked link.
- `README.md`
  - Added Atlas Cloud to the repository-level RAG provider summary.

## Notes

- The Atlas Cloud base URL is `https://api.atlascloud.ai/v1`.
- The default working model is `deepseek-ai/DeepSeek-V3-0324`.
- The generic `deepseek-v3` alias from Atlas docs did not work for the
  provided key during live testing, so the integration now uses a model ID
  verified via the live `/models` endpoint.
- The real API key is stored only in local `5.RAG/.env.local` and is not
  intended to be committed.

## Validation

- Unit tests: `pytest tests/test_llm_provider.py -q`
- Live Atlas integration: `pytest tests/test_integration.py -q -k AtlasCloudIntegration`
- Combined run with local env: `pytest tests/test_llm_provider.py tests/test_integration.py -q`
- App smoke start: `streamlit run src/app.py --server.headless true --server.port 8503`
