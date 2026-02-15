# Reth + Lighthouse (Docker Compose)

Standalone Docker Compose for running an Ethereum node with [Reth](https://github.com/paradigmxyz/reth) (execution layer) and [Lighthouse](https://github.com/sigp/lighthouse) (consensus layer).

Supports both **full** and **archive** node modes via Docker Compose profiles.

> **Note:** Production deployments use Ansible (`ansible/roles/ethereum/`). This compose file is for testing, development, and standalone setups.

## Node Modes

| Profile | Reth | Lighthouse | Use Case |
|---------|------|------------|----------|
| `full` | `--full` (pruned) | Standard beacon node | General-purpose node, lower disk usage |
| `archive` | No flag (stores everything) | `--reconstruct-historic-states`, `--supernode`, `--prune-blobs=false` | Full historical state, L2 beacon endpoint |

### Reth Mode Behavior

- `--full` = **full node** (enables pruning, discards old receipts/history)
- No flag = **archive node** (stores all historical state, no pruning)

## Quick Start

```bash
# 1. Generate JWT secret for EL <-> CL communication
openssl rand -hex 32 > jwt.hex

# 2. Configure environment
cp .env.example .env
# Edit .env - set RETH_VERSION, LIGHTHOUSE_VERSION, DATA_DIR, etc.

# 3. Start as full node (pruned)
docker compose --profile full up -d

# 3. OR start as archive node (all historical state)
docker compose --profile archive up -d

# View logs
docker compose logs -f

# Stop
docker compose --profile full down
# or
docker compose --profile archive down
```

## Ports

| Port | Protocol | Service | Description |
|------|----------|---------|-------------|
| 30303 | TCP/UDP | Reth | P2P discovery and sync |
| 8545 | TCP | Reth | HTTP JSON-RPC |
| 8546 | TCP | Reth | WebSocket JSON-RPC |
| 8551 | TCP | Reth | Engine API (internal) |
| 9000 | TCP/UDP | Lighthouse | P2P discovery |
| 9001 | UDP | Lighthouse | QUIC transport |
| 5052 | TCP | Lighthouse | Beacon HTTP API |

## L2 Beacon Endpoint (Archive Only)

Archive nodes with `--prune-blobs=false` and `--supernode` serve blob data for L2 chains:

```bash
curl http://localhost:5052/eth/v1/beacon/blob_sidecars/head
```

Used by Arbitrum, Optimism, Base, and other L2s that need historical blob data.
