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

## E: video contract

`tests/playwright/ai-video-fullstack.spec.js` obtains and approves a real Worker
generated PowerPoint, selects it in the video UI, clicks the formal generation
button, polls the real job, and inspects actual MP4 bytes from both preview and
S3. FFmpeg must successfully decode the output and report a positive duration
matching the persisted timeline. Hash, MIME, model/voice, renderer and segment
metrics are verified. Both captions are read from their formal routes.
The real UI MP4 link opens the stored video; Linux CI runs this E contract in
branded Google Chrome, asserts H.264/AAC codec support, verifies byte-range
delivery, requires a positive browser duration, and requires playback time to
advance. Bundled Windows Chromium may lack the OS H264 decoder; local Windows
runs still require real FFmpeg decoding. Browser failure in Linux CI is not
replaced by the FFmpeg result.
Teacher approve/publish buttons create a receipt and a canonical material
derivative, whose persisted version ledger is read again through the real API.

The isolated runner deliberately requests legacy `mega` video storage while
using the existing R2 fallback. It disables PowerPoint COM, isolates caches and
lets the unchanged renderer chain choose LibreOffice or safe text rendering.
CI already installs actual FFmpeg/LibreOffice; no video pipeline is replaced.
The full-stack test exposed and fixed two production issues: preview must
redirect signed provider URLs, and `.tmp` segment outputs require the explicit
FFmpeg MP4 muxer. Formal Kokoro/R2/account acceptance is still separate.
