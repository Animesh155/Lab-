# OPC UA security flip — instructor notes

Two shell scripts that swap the `plc-opcua` container between its
two security postures without rebuilding the image.

| Script | What it does |
|---|---|
| `up.sh` | Kills `plc-opcua`, relaunches the same image with `OPCUA_SECURITY=basic256sha256`. The Python server generates a self-signed cert at first start (`openssl req -x509 ...`) and binds the endpoint with `Basic256Sha256_SignAndEncrypt`. |
| `down.sh` | Kills the secure container and recreates `plc-opcua` via `docker compose` so the original env (`OPCUA_SECURITY=none` implicit) is restored. |

## How it works

The same `phase1_env/ot_simulators/opcua_plc/opcua_server.py` honors
an `OPCUA_SECURITY` env var:

- `none` (default) → `set_security_policy([NoSecurity])`, anonymous OK
- `basic256sha256` → generates cert+key in `/app/certs/` on first run,
  loads them, and advertises only `Basic256Sha256_SignAndEncrypt`

The attack tool (`/lab/tools/attack.py`) is unaware of any of this. It
just connects with no policy and no cert, which works against the
open server and fails with `BadSecurityChecksFailed` against the
secure one. That's the whole pedagogical payload.

## Why both scripts use `docker rm` not `docker compose stop`

`compose stop` keeps the container's existing env. We need the env to
change. The cleanest way is to nuke and recreate.

## Cert hygiene

The cert is generated *inside* the container the first time it starts
in secure mode. It lives in the container's writable layer (NOT a
mounted volume) so it's thrown away with the container on `down.sh`.
That keeps the lab reproducible — every secure-mode session gets a
fresh cert, no stale-key surprises.

For a multi-student deployment you'd want to bind-mount a volume so
each student's container has a stable cert across restarts. Trivial
to add — for now, throwaway is fine.
