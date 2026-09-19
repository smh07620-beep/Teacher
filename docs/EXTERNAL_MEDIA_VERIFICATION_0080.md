# External media verification — migration 0080

`0080-external-media-verification` adds bounded availability metadata to the
existing `external_media` table. It does not create a second material store and
does not change `/ready`, publication state, or material deletion behavior.

## Canonical providers and allowlist

External teaching video URLs are accepted only when they use HTTPS and match
one of these contracts:

- YouTube: known YouTube input hosts. The stored identity remains the canonical
  `https://www.youtube.com/watch?v=...` URL, while playback uses the
  `https://www.youtube-nocookie.com/embed/...` privacy contract.
- Vimeo: known Vimeo/player hosts and the canonical `https://vimeo.com/<id>`
  identity.
- Hospital CDN: an exact hostname explicitly listed in
  `EXTERNAL_MEDIA_HOSPITAL_CDN_HOSTS`, with an `.mp4` or `.webm` path.

There is no built-in permissive direct-media hostname and no wildcard host
matching. `localhost`, raw private/loopback/link-local addresses and similar
internal targets are rejected unless that exact hostname/IP literal is
explicitly configured as a hospital CDN. This exception does not relax redirect
checking: server verification never follows a redirect outside the fixed
provider hosts or the exact configured hospital CDN host set.

Example Render/environment setting:

```text
EXTERNAL_MEDIA_HOSPITAL_CDN_HOSTS=video-cdn.hospital.example,training-media.hospital.example
```

Do not include schemes, paths, ports, or wildcards in this setting.

## Availability metadata

Migration 0080 adds these additive columns to `external_media` on both SQLite
and PostgreSQL:

- `last_verified_at`
- `availability_status` (`unverified`, `available`, `unavailable`, `error`)
- `last_error`
- `provider_metadata` (JSONB on PostgreSQL, JSON text on SQLite)

Verification is diagnostic only. A failed check does not delete, unpublish, or
disable the material and is not part of the application readiness probe.

## Verification behavior

YouTube and Vimeo use their fixed oEmbed/provider endpoints with bounded
responses and bounded redirect depth. Hospital CDN URLs use a bounded `HEAD`,
with a bounded ranged `GET` fallback when needed, and accept only approved video
content types. Redirect destinations are revalidated before each request.

The admin report is available at `GET /api/external-media/report` to principals
with `audit.read` or `material.manage`. Auditors remain read-only. A manual
verification is `POST /api/materials/<material_id>/external-media/verify` and
requires `material.manage` with the existing material group scope rules.

## Periodic scheduler

A host scheduler can safely run:

```text
python -m teacher_app.maintenance.external_media_verify --older-than-minutes 360 --limit 100
```

A practical default is every 6 hours (`360` minutes). Keep each run bounded and
prefer modest batches (for example 50–100 rows). The command only verifies rows
whose last check is older than the requested interval and writes availability
metadata; it performs no material deletion or publication changes.
