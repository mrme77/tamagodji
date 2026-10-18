# Tamagodji

A small virtual pet designed to run on a Raspberry Pi 3 with a 0.96-inch I²C
SSD1306 OLED, two USB-connected micro:bits, and a USB microphone.

## Development model

Develop and test on a Mac in `mock` mode. Deploy the same repository to the Pi and
run `hardware` mode there. The pet logic and SQLite persistence are shared between
both environments; only the display and sensor adapters change.

## Run on a Mac

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m tamagodji --mode mock --demo
```

For interactive development:

```bash
python -m tamagodji --mode mock
```

Available commands are `feed`, `pet`, `light 0-100`, `sound 0-100`, `tick`, and
`quit`.

The pet's needs use persisted elapsed time rather than loop count. Fullness falls
slowly while awake and more slowly while asleep. Darkness and daylight create
one-time `Good night!` and `Good morning!` messages. Prolonged hunger can make the
pet sick, but feeding it can recover the pet; there is no permanent death in this
version. In hardware mode, the OLED also shows the Raspberry Pi CPU temperature;
this is a system temperature, not the room temperature.

Run tests with:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

Pull requests run the same tests on Python 3.10, 3.11, and 3.14 via GitHub Actions.
The tests use mocked hardware and local HTTP servers, never the live Pi.

## Raspberry Pi setup

Clone the repository on the Pi, enable I²C, and install the optional hardware
dependencies:

```bash
git clone <your-github-repository-url> tamagodji
cd tamagodji
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m pip install -r requirements-pi.txt
```

The OLED wiring is:

```text
OLED GND → Pi pin 6 (GND)
OLED VCC → Pi pin 1 (3.3V)
OLED SCL → Pi pin 5 (GPIO3 / SCL)
OLED SDA → Pi pin 3 (GPIO2 / SDA)
```

Start hardware mode after identifying the two serial ports:

```bash
python -m tamagodji --mode hardware \
  --interaction-port /dev/ttyACM0 \
  --room-port /dev/ttyACM1
```

### Run automatically at boot

The repository includes a `systemd` service configured for the current Pi user
(`mrme77`) and the stable `/dev/serial/by-id/` paths for the two micro:bits. After
pulling the repository on the Pi, install and start it with:

```bash
sudo cp deploy/tamagodji.service /etc/systemd/system/tamagodji.service
sudo systemctl daemon-reload
sudo systemctl enable tamagodji
sudo systemctl start tamagodji
sudo systemctl status tamagodji
```

View live application logs with:

```bash
sudo journalctl -u tamagodji -f
```

The service restarts the application after a failure and starts it again after a
Pi reboot. The SQLite state remains in `.data/pet.db`. The service also selects the
USB microphone explicitly so ALSA's default device does not change its behavior
after a reboot. Install offline voice output on the Pi with:

```bash
sudo apt update
sudo apt install espeak-ng
```

The micro:bit message format is documented in
[`docs/microbit-protocol.md`](docs/microbit-protocol.md). The local API and its
website/tunnel guidance are documented below.

In hardware mode, the Pi speaks `Good morning, fellas! I am awake!` and `Good
night, fellas! I am going to sleep!` through the configured audio output. Voice
errors are logged without stopping the OLED or pet service. A powered speaker or
amplifier is required for the Pi's line-level 3.5 mm output.

USB microphone input is optional. The boot service currently disables it so a
problematic microphone cannot stop the pet, display, or voice greetings. Re-enable
it later with `TAMAGODJI_MICROPHONE_ENABLED=1` after testing the USB audio device.

## Local API and website display

Hardware mode starts a small JSON API on `127.0.0.1:8080`. It runs inside the
same process as the pet. Only the hardware loop advances and persists state;
API reads return its most recent state without SQLite writes or sensor reads.
Commands use a bounded queue, with a small processing budget per loop iteration.

Check it from the Pi with:

```bash
curl http://127.0.0.1:8080/api/health
curl http://127.0.0.1:8080/api/pet
```

The state response includes the pet meters, mood, CPU temperature, aggregate
website interaction counts, and the text frame currently suitable for the OLED.
The OLED frame includes the Pi's current time in 24-hour format. Website actions use:

```bash
curl -X POST http://127.0.0.1:8080/api/interactions \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TAMAGODJI_API_TOKEN" \
  -d '{"action":"feed"}'
```

The accepted actions are `feed` and `play`. Website actions are stored only as
anonymous aggregate counters (`feed`, `play`, and `total`). Sleeping actions are
rejected with HTTP 409; an action queued just before sleep is ignored and not
counted. These counters do not store visitor identities or message contents.
Hosting, tunnel, and model providers have their own logging/data policies; this
is not a claim that the complete website is automatically GDPR compliant.
The API initially binds only to the
Pi itself. For a public website, put it behind a Cloudflare Tunnel and set a
long random `TAMAGODJI_API_TOKEN` in the Pi's private `.env` file. All write
requests, including localhost tests, must send `Authorization: Bearer <token>`.
If the token is missing or blank, writes are disabled (HTTP 503), while the
display and health endpoints remain available. A wrong/missing bearer header
returns HTTP 401. Use a randomly generated token of at least 32 bytes. Keep the
website origin in `TAMAGODJI_CORS_ORIGIN`, for example
`https://pasqualesalomone.com`. Do not put the token in public browser code; a
public website should normally call a small server-side proxy for write actions.

The examples assume the token is already in your terminal environment; systemd's
environment is not automatically inherited by an SSH shell. Never paste the
actual token into Git, screenshots, browser code, or chat messages.

The Pi enforces a global five-second action cooldown, a one-minute chat cooldown,
one concurrent model call, and a bounded 16-command queue. Excess requests return
429 (cooldown) or 503 (busy), with `Retry-After`. Reads allow a burst of 20, then
10 per second across all visitors. These limits do not identify visitors and
reset on service restart. The website should show the returned error and avoid
automatic retries for commands. `202 accepted` means queued, not yet applied.
Audio runs on one worker with two waiting announcements; excess announcements
are skipped with a warning, without dropping the underlying pet action.

See [the security review and deployment checklist](docs/security-review.md) for
the trust boundaries, remaining risks, and safe rollout instructions.

When the Pi is powered off, both this API and the Cloudflare Tunnel origin are
offline. The installed `cloudflared` service starts again at boot when the Pi is
powered on. Cloudflare Tunnel uses outbound connections, so the Pi does not need
an inbound router port opened; the website still needs the API token configured
in its server-side proxy before public write actions are enabled.

## OpenRouter LLM brain

The deterministic pet state machine remains authoritative for sleep, light,
food, energy, sickness, and persistence. OpenRouter adds personality and chat;
it does not receive permission to write the database or invent hardware commands.
The Pi sends the current state and a user message to the OpenRouter chat
completions endpoint. The expected result is a short reply plus one optional
validated action: `FEED`, `PLAY`, or `NONE`.

Configure it only on the Pi, never in website JavaScript or Git:

```bash
cp -n .env.example .env
chmod 600 .env
nano .env
```

Do not overwrite an existing `.env`. Uncomment and set `OPENROUTER_API_KEY`,
`TAMAGODJI_API_TOKEN` (unless already supplied by a service override), and,
optionally, `OPENROUTER_MODEL`. The service loads
`.env` at boot. Without a key, `/api/chat` returns a clear not-configured
response and the rest of the pet continues working offline. With a key, a chat
request looks like:

```bash
curl -X POST http://127.0.0.1:8080/api/chat \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TAMAGODJI_API_TOKEN" \
  -d '{"message":"I am here to take care of you"}'
```

Both the bearer token and an OpenRouter key are required for chat. Set a spending
limit on the provider key as well: request throttling is not a monetary budget.
The API implementation uses OpenRouter's OpenAI-compatible
`/api/v1/chat/completions` endpoint. For a website, the safest first version is
read-only polling of `/api/pet` every 2–5 seconds; add authenticated actions
through a server-side website route after the display is working.

## Flash the micro:bits

The two MicroPython programs are in [`microbit/`](microbit/):

- [`interaction.py`](microbit/interaction.py) goes on the handheld controller.
- [`room_sensor.py`](microbit/room_sensor.py) goes on the fixed room-light sensor.

See [`microbit/README.md`](microbit/README.md) for the flashing steps. After both
micro:bits are connected to the Pi, identify their serial ports and start hardware
mode with those two paths.
