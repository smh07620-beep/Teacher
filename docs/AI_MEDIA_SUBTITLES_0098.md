# AI media subtitles — 0098

Migration `0098-media-subtitles` adds a persistent subtitle queue and reviewed subtitle records without changing the existing material store.

## Supported sources

- Uploaded video/audio: supported by the dedicated AI Worker.
- Allowed hospital CDN direct MP4/WebM: supported only when the exact host is present in `EXTERNAL_MEDIA_HOSPITAL_CDN_HOSTS` on the trusted Worker.
- YouTube/Vimeo iframe media: Teacher does not download or proxy the original media. Platform-provided captions continue to belong to the provider; Teacher-generated captions fail closed for these sources.

## AI/runtime policy

Subtitle jobs run only in `ai_question_worker.py`, never inside the Render Web request. When `AI_EXTERNAL_MEDIA_ALLOWED=false` (the production default), raw audio/video is not sent to cloud AI and the Worker uses local `faster-whisper`. If external media AI is explicitly enabled and `GROQ_API_KEY` is configured, Groq Whisper may be used; only quota/rate-limit/transient provider failures may fall back to local Whisper. Deterministic validation or malformed-output errors do not provider-hop.

`GEMINI_API_KEY` remains part of the free text/model fallback chain (`Groq -> Gemini -> Ollama`) but is not used as the speech-to-text engine for subtitle timing.

## Review and publication

AI output is stored as a `draft` WebVTT/SRT record. Teachers with scoped `material.manage` permission may edit the WebVTT and explicitly approve it. Learner playback only receives `approved` subtitles whose `source_version` still matches the material's current version. Publishing a newer material version therefore invalidates the old caption for playback until a new subtitle is generated and approved.

Approved HTML5 video subtitles are loaded as a same-origin `<track kind="subtitles">`. The VTT/SRT endpoints enforce the same material audience policy before returning caption content.

## Provenance

Each subtitle stores provider/model, fallback state, source material version, SHA-256 of the audio artifact actually transcribed, source kind/locator, source job id, creator/editor/approver and timestamps.

## Environment

Render Web declares `GEMINI_API_KEY` as `sync: false` so a manually configured secret is retained outside source control. The trusted local AI Worker needs its own `.local-worker.env`; Render secrets are not inherited by the local process. For local subtitles keep:

```text
AI_EXTERNAL_MEDIA_ALLOWED=false
LOCAL_WHISPER_ENABLED=true
LOCAL_WHISPER_MODEL=small
LOCAL_WHISPER_DEVICE=cpu
LOCAL_WHISPER_COMPUTE_TYPE=int8
```

Set `AI_EXTERNAL_MEDIA_ALLOWED=true` only after an explicit privacy decision if raw media may be sent to Groq transcription.
