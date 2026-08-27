# Drowned Remote Relay

Provider-neutral relay service for Drowned Control.

The relay does not download games, inspect download sources, or persist screen frames. It only forwards authenticated commands/status messages between one Windows Agent and the mobile app. In-memory mobile queues are bounded and old screen frames are purged when a test ends.

## Run

Python 3.12+ is recommended.

```bash
python -m pip install -r requirements.txt
export DROWNED_REMOTE_TOKEN="use-a-long-random-secret"
uvicorn server:app --host 0.0.0.0 --port 8080
```

On Windows PowerShell, set the token with `$env:DROWNED_REMOTE_TOKEN="..."` before starting Uvicorn.

## Public hosting

The service can run on any VPS or hosting platform that supports Python ASGI, HTTPS and WebSockets. Put it behind HTTPS/TLS for internet use.

- Agent WebSocket base: `wss://YOUR-HOST/ws`
- Mobile HTTPS base: `https://YOUR-HOST`
- Health endpoint: `https://YOUR-HOST/health`

No home IP address is stored in the app. The PC creates an outbound WebSocket connection to the relay, so changing home/VPN IP addresses does not change the device identity.

## Authentication

Set the same long random `DROWNED_REMOTE_TOKEN` on the relay and in the paired Agent/mobile client. The current MVP is intentionally scoped to a single trusted PC/device setup.
