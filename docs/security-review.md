# Security review and hardening

Reviewed 2026-10-18 against main `fbe3c73`; changes live on
`codex/security-hardening` until reviewed and merged. This is a source review and
local regression test exercise, not a penetration test or security certification.
No live commands, paid model calls, or production configuration changes were made.

## Scope and trust boundaries

Reviewed the Python API, event loop, persistence, hardware adapters, model client,
service configuration, firmware protocol, tests, and deployment instructions.
Also inspected the website's `/api/tamagodji` proxy for compatibility, without
editing that separate repository or auditing its other features.

Visitors call the website proxy; the proxy attaches the shared bearer token and
calls the Pi through Cloudflare Tunnel. The token authenticates the proxy, not
individual visitors. The Pi therefore enforces its own global limits, independent
of browser UI restrictions or client-supplied IP/forwarding headers.

## Findings addressed

| Priority | Finding | Change |
| --- | --- | --- |
| High | Missing token silently enabled commands, including through a localhost tunnel | Fail-closed writes; constant-time credential comparison |
| High | Anonymous proxy actions could fill an unlimited command queue and monopolize the loop | Shared action cooldown, finite queue, nonblocking admission, four-command loop budget |
| High | Unlimited HTTP worker allocation and waiting on incomplete bodies | Eight connection slots, five-second socket inactivity timeout, bounded bodies and explicit framing checks |
| Medium | Public reads advanced the simulation and wrote SQLite | Read-only snapshots with cached temperature; loop owns persistence |
| Medium | Speech held the state lock and paused hardware polling | Separate bounded audio worker; no speech inside the state lock |
| Medium | Model text was passed as an espeak command-line argument | Text passed through stdin and bounded to 180 characters |
| Medium | Chat could trigger concurrent paid inference and unbounded response reads | One inference at a time, minute cooldown, 64 KiB response ceiling |
| Medium | Blank example environment assignments overrode working service settings | Optional serial/token/key overrides commented out; non-overwriting setup instructions |
| Medium | Partial USB serial lines could create false light readings | Bounded receive buffer; parse complete lines only |
| Low | Sleeping no-op actions inflated aggregate counters | Count only awake web actions; HTTP 409 when already asleep |
| Low | SQLite connection context managers did not explicitly close connections | Explicit connection closing and transactional saves |
| Defense in depth | Service could inherit broader privileges than required | No privilege escalation, no capabilities, restrictive new-file permissions, read-only system paths and protected kernel settings |

The systemd environment-file precedence is documented in the
[systemd manual](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#EnvironmentFile=).
A copied blank `TAMAGODJI_API_TOKEN=` can override a populated `Environment=`
drop-in: remove that blank assignment or set the intended token privately.

## Deliberate limits and remaining work

- Keep port 8080 on loopback, with Cloudflare terminating HTTPS. Do not expose
  the HTTP listener directly to the Internet or open a router port. The custom
  bounded listener still builds on `http.server`, which Python
  [does not recommend as a general production server](https://docs.python.org/3/library/http.server.html).
  A maintained production HTTP stack is a follow-up before scaling this service.
- Socket timeouts are inactivity limits, not total request deadlines. A client
  sending data slowly can occupy a finite slot; edge rate/connection protections
  are still needed. Local bounds protect memory, not universal availability.
- Global cooldowns are intentionally simple and store no visitor identifiers.
  A persistent bot could still consume the shared allowance. Add edge abuse
  controls to the website and tunnel; the website's Vercel invocation costs are
  not protected by the Pi's rate limit. The proxy currently forwards statuses
  and JSON errors but not the upstream `Retry-After` header.
- The token must stay server-side and must match between Vercel and the Pi.
  CORS is not authentication. Public reads intentionally reveal the pet's room
  light/sleep state and Pi temperature. Provider access logs are separate from
  aggregate-only counters; this review does not establish GDPR compliance.
- Set an OpenRouter key spending limit before enabling chat. Rate limits are
  in-memory and reset on restart; they do not constitute durable cost quotas.
  Model messages and state are sent to the provider. No inference was tested
  against the real provider in this review.
- Hardware dependency requirements use version ranges, not a reproducible lock.
  The installed Pi packages and OS were not vulnerability-scanned. Capture and
  audit those actual versions before claiming a dependency audit is complete.
- The service still runs as the existing login user to preserve known device
  access. A dedicated service account and tighter filesystem/device policies
  require a separate Pi compatibility test. Existing files are not chmodded by
  `UMask=0077`; keep `.env` private and protect database backups.
- Database corruption/schema validation and the long-offline neglect calculation
  need a separate reliability pass. Back up the state; do not delete it to
  resolve startup errors. This change does not alter hunger/sickness timing.

The long-offline calculation currently applies the entire elapsed interval to
neglect when hunger crosses 95 during that interval. This can make sickness
arrive earlier after downtime than with frequent ticks. It is a gameplay
correctness issue, separate from the public-API security changes.

## Validation

Local results: **70 tests passed on Python 3.10 and Python 3.14**, with resource
warnings treated as errors. Python source compilation and `git diff --check`
also passed. These results do not validate the Pi's physical devices or Linux
service restrictions.

Run `python -m pytest -q` from a development environment. Regression coverage
includes missing/wrong tokens, malformed and oversized JSON, cooldowns, full
queues, incomplete request bodies, HTTP connection saturation, sleeping actions,
concurrent reads during speech, bounded audio failures, model response limits,
and fragmented serial messages. All API tests bind ephemeral loopback ports;
hardware and model calls are mocked. Physical device and systemd behavior still
require the Pi smoke test below.

CI is configured for Python 3.10, 3.11 (the Pi's Python series), and 3.14, using
commit-pinned actions and a read-only repository token. The workflow has not yet
run remotely because this branch has not been pushed. A limited common-pattern
scan of tracked non-test files found no private-key blocks, OpenRouter key
strings, or GitHub personal tokens; that is not an exhaustive secret-history audit.

## Deployment checklist — after PR review and merge

1. Preserve the current commit ID and back up `.data/pet.db` consistently (stop
   the service while copying, or use SQLite's backup facility). Preserve `.env`
   and service overrides privately. Never commit them or paste their contents.
2. Check that the Pi has a nonempty, strong API token and Vercel has the same
   token. Remove blank serial overrides from `.env`; don't replace that file
   with the new example. A missing token now intentionally disables commands.
3. Pull the reviewed main branch and install the revised service file. Reload
   systemd and restart Tamagodji. No new application dependencies are required.
4. Confirm the service stays active, then check `/api/health` locally and through
   the tunnel. Check real `/api/pet` values, both micro:bits, OLED, and voice.
   Pay particular attention to audio and USB permissions after service hardening.
5. While awake, send one website Feed action: expect acceptance and one count
   increment after the next loop. Immediately repeat: expect 429, without a
   second change. Wait at least five seconds before a different action. While
   asleep, expect 409 and unchanged counters.
6. Confirm an unauthenticated POST is rejected, and that the site handles busy,
   cooldown, sleeping, and offline responses without automatic command retries.
   Do not load-test the live Pi. Restart once and verify the pet state survives.
7. If the smoke test fails, stop the service and restore the recorded code and
   service version; reload and restart. Do not reset or remove the database.
