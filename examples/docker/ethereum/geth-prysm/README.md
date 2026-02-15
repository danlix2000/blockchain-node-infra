# Geth + Prysm (Docker Compose)

Standalone Docker Compose for running an Ethereum full node with [Geth](https://github.com/ethereum/go-ethereum) (execution layer) and [Prysm](https://github.com/prysmaticlabs/prysm) (consensus layer).

> **Note:** Production deployments use Ansible (`ansible/roles/ethereum/`). This compose file is for testing, development, and standalone setups.

## Quick Start

```bash
# 1. Generate JWT secret for EL <-> CL communication
openssl rand -hex 32 > jwt.hex

# 2. Configure environment
cp .env.example .env
# Edit .env - set GETH_VERSION, PRYSM_VERSION, DATA_DIR, etc.

# 3. Start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

## Ports

| Port | Protocol | Service | Description |
|------|----------|---------|-------------|
| 30303 | TCP/UDP | Geth | P2P discovery and sync |
| 8545 | TCP | Geth | HTTP JSON-RPC |
| 8546 | TCP | Geth | WebSocket JSON-RPC |
| 8551 | TCP | Geth | Engine API (internal) |
| 13000 | TCP | Prysm | P2P TCP |
| 12000 | UDP | Prysm | P2P UDP |
| 3500 | TCP | Prysm | gRPC Gateway (Beacon HTTP API) |

## Sync Mode

Geth uses `--syncmode=snap` for fast initial sync. This downloads state snapshots rather than replaying all historical transactions. Suitable for full nodes that don't need historical state access.
