# Audio / video full-stack E2E

## D: completed audio contract

`tests/playwright/ai-audio-fullstack.spec.js` uses the shared isolated runner.
It creates an approved script through existing routes, selects it and a voice
in the real narration UI, clicks preview and formal generation, and polls the
canonical persisted jobs processed by the canonical HTTPS AI Worker.
`tests/inspect_media_artifact.py` reads the actual Moto S3 object and validates
RIFF/WAVE headers, byte size, sample rate, channels and duration. The browser
loads and plays the preview. Formal output is verified in canonical material
listing with script provenance, teacher approval, voice, provider and model.

The worker advertises deterministic TTS readiness only with BOTH
`TEACHER_E2E_TEST_MODE=1` and `TEACHER_E2E_DETERMINISTIC_STUBS=1`.
Neither switch alone changes production capabilities. No Kokoro model is
downloaded in CI; production acceptance must still verify actual Kokoro.
Browser fetch, routes, DB, queues, Worker transport and storage are not mocked.
