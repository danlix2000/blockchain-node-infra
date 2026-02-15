# Block Lag & Latency Monitor

Multi-endpoint RPC monitoring tools that measure block lag, RPC latency, and estimate sync ETA for blockchain nodes.

## Scripts

| Script | Target Chains | Description |
|--------|---------------|-------------|
| `blocklag_monitor.py` | Any EVM chain | General-purpose monitor using `eth_getBlockByNumber` |
| `blocklag_monitor_avax.py` | Avalanche C-Chain, subnets, L1s | Avalanche-optimized with PoA/extraData middleware and target-lag ETA |

Both scripts share the same `endpoints.json` config and `web3>=6.0.0` dependency.

### EVM Compatibility

`blocklag_monitor.py` works with **any EVM-compatible chain** that supports the standard `eth_getBlockByNumber("latest")` JSON-RPC method. This includes:

- Ethereum (Mainnet, Sepolia, Holesky)
- BNB Smart Chain
- Polygon
- Arbitrum, Optimism, Base
- Avalanche C-Chain
- Any EVM-compatible L2/L3 or appchain

Chain names are auto-detected via `eth_chainId` and enriched using [ChainList](https://chainlist.org).

### Avalanche Script

`blocklag_monitor_avax.py` adds Avalanche-specific handling:

- **PoA/extraData middleware** - Avalanche nodes return `extraData` fields longer than 32 bytes, which triggers validation errors in web3.py. The script injects the appropriate middleware automatically.
- **Target-lag ETA** - Instead of estimating time to zero lag, it estimates time to reach a configurable threshold (default `<= 5s`), which is more practical for Avalanche's fast block times (~2s).
- **Subnet/L1 support** - Works with any Avalanche-based subnet or L1 via the standard `/ext/bc/<chain>/rpc` endpoint path.

## What It Measures

For each configured RPC endpoint, the tools poll `eth_getBlockByNumber("latest")` repeatedly and report:

| Metric | Description |
|--------|-------------|
| **RPC Latency** | Round-trip time (ms) for each `eth_getBlockByNumber` call |
| **Block Lag** | `wall_clock_now - latest_block.timestamp` (how far behind the chain tip) |
| **Sync ETA** | Estimated time to catch up, based on a windowed trend of decreasing block lag |
| **Chain ID** | Auto-detected via `eth_chainId`, enriched with chain name from [ChainList](https://chainlist.org) |
| **Client Version** | Detected via `web3_clientVersion` (e.g., `Reth/v1.9.4`, `AvalancheGo/v1.12.0`) |

## Prerequisites

- Python >= 3.10
- Network access to the RPC endpoints you want to monitor

## Setup

```bash
cd tools/block-lag-monitor

# Option A: Use the project's existing virtual environment
source ../../.venv/bin/activate
pip install -r requirements.txt

# Option B: Create a dedicated virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy the example config and add your endpoints:

```bash
cp endpoints.json.example endpoints.json
```

Edit `endpoints.json` - a JSON object where each key is a **group name** and the value is a dict of `name -> URL`:

```json
{
    "eth-mainnet": {
        "mainnet-archive-aws-1": "http://10.10.0.100:8545",
        "mainnet-archive-aws-2": "http://10.10.0.101:8545",
        "mainnet-full-latitude-1": "http://203.0.113.50:8545"
    },
    "avalanche-mainnet": {
        "avax-node-1": "http://10.40.0.100:9650/ext/bc/C/rpc",
        "avax-node-2": "http://10.40.0.101:9650/ext/bc/C/rpc"
    },
    "dexalot-mainnet": {
        "dexalot-full-1": "http://10.50.0.100:9650/ext/bc/SUBNET_ID/rpc"
    }
}
```

> **Security:** `endpoints.json` contains real endpoint URLs and may include API keys. It is gitignored - do not commit it.

### Avalanche RPC Paths

| Network | Default RPC Path |
|---------|-----------------|
| C-Chain | `/ext/bc/C/rpc` |
| Subnets/L1s | `/ext/bc/<SUBNET_ID>/rpc` |

## Usage

### EVM Monitor (Ethereum, BNB, Polygon, etc.)

```bash
# Monitor Ethereum mainnet endpoints (default: 30s duration, ~11 polls/sec)
python3 blocklag_monitor.py eth-mainnet

# Monitor Sepolia testnet
python3 blocklag_monitor.py eth-sepolia

# Monitor BNB archive nodes
python3 blocklag_monitor.py bnb-mainnet

# Custom duration (60s) and polling rate (one call every 0.2s)
python3 blocklag_monitor.py eth-mainnet --duration 60 --rate 0.2

# Increase ETA estimation window for nodes doing initial sync
python3 blocklag_monitor.py eth-sepolia --eta-window 120

# Use a custom config file
python3 blocklag_monitor.py eth-mainnet --config /path/to/endpoints.json

# Disable ChainList lookup (use built-in chain name map only)
python3 blocklag_monitor.py eth-mainnet --no-chainlist

# Show Network ID column (net_version, for diagnostics)
python3 blocklag_monitor.py eth-mainnet --show-netid
```

### Avalanche Monitor

```bash
# Monitor Avalanche C-Chain nodes
python3 blocklag_monitor_avax.py avalanche-mainnet

# Monitor a subnet/L1 (e.g., Dexalot)
python3 blocklag_monitor_avax.py dexalot-mainnet

# Custom duration and polling rate
python3 blocklag_monitor_avax.py avalanche-mainnet --duration 60 --rate 0.5

# Change sync threshold (default: 5s lag = synced)
python3 blocklag_monitor_avax.py avalanche-mainnet --target-lag 10

# Increase ETA smoothing window (more samples)
python3 blocklag_monitor_avax.py avalanche-mainnet --eta-window 60
```

## Example Output

### EVM Monitor

```
2026-02-11 - INFO - Loading endpoints from endpoints.json (group=eth-mainnet)
2026-02-11 - INFO - Loaded 2847 chain names from ChainList (cache/API).
2026-02-11 - INFO - Testing for 30 s at one call every 0.09 s …
2026-02-11 - INFO - Average metrics after the test completes:
Endpoint                                       AvgLatency (ms)     AvgBlockLag             ETA        Block                      Chain          ChainId Client Version
==========================================================================================================
[mainnet-archive-aws-1                     ]           42.31              2s              0s   21,456,789          Ethereum Mainnet        1 / 0x1 Reth/v1.9.4
[mainnet-archive-aws-2                     ]           38.56              1s              0s   21,456,789          Ethereum Mainnet        1 / 0x1 Reth/v1.9.4
[mainnet-full-latitude-1                   ]           85.22              3s              0s   21,456,789          Ethereum Mainnet        1 / 0x1 Geth/v1.16.8
```

### Avalanche Monitor

```
2026-02-11 - INFO - Loading endpoints from endpoints.json (group=avalanche-mainnet)
2026-02-11 - INFO - Loaded 2847 chain names from ChainList (cache/API).
2026-02-11 - INFO - Testing for 30 s at one call every 0.20 s …
2026-02-11 - INFO - Average metrics after the test completes:
Endpoint                          AvgLatency (ms)  AvgBlockLag        ETA<=5s        Block            ChainId Chain                        Client Version
==========================================================================================================
[avax-node-1                   ]           25.10           2s         SYNCED      98,765,432   43114 / 0xa86a Avalanche C-Chain Mainnet    avalanchego/v0.15.4
[avax-node-2                   ]           31.44           3s         SYNCED      98,765,432   43114 / 0xa86a Avalanche C-Chain Mainnet    avalanchego/v0.15.4
```

## CLI Reference

### `blocklag_monitor.py` (EVM)

| Flag | Default | Description |
|------|---------|-------------|
| `group` | *(required)* | Group name from `endpoints.json` |
| `--duration`, `-d` | `30` | Test duration in seconds |
| `--rate`, `-r` | `0.09` | Delay between RPC polls (seconds) |
| `--eta-window` | `30` | Seconds of history for ETA calculation |
| `--config`, `-c` | `endpoints.json` | Path to config file |
| `--show-netid` | off | Show `net_version` column |
| `--no-chainlist` | off | Disable ChainList chain name enrichment |
| `--chainlist-allow-stale` | off | Use stale cache if ChainList fetch fails |
| `--chainlist-ttl` | `86400` | ChainList cache TTL (seconds) |

### `blocklag_monitor_avax.py` (Avalanche)

| Flag | Default | Description |
|------|---------|-------------|
| `group` | *(required)* | Group name from `endpoints.json` |
| `--duration`, `-d` | `30` | Test duration in seconds |
| `--rate`, `-r` | `0.20` | Delay between RPC polls (seconds) |
| `--target-lag` | `5` | Block lag threshold (seconds) for "SYNCED" ETA |
| `--eta-window` | `20` | Number of recent samples for ETA smoothing |
| `--config`, `-c` | `endpoints.json` | Path to config file |
| `--show-netid` | off | Show `net_version` column |
| `--no-chainlist` | off | Disable ChainList chain name enrichment |
| `--chainlist-allow-stale` | off | Use stale cache if ChainList fetch fails |
| `--chainlist-ttl` | `86400` | ChainList cache TTL (seconds) |

## How It Works

1. Loads endpoint group from `endpoints.json`
2. Optionally fetches chain names from [ChainList](https://chainlist.org) (cached for 24h at `~/.cache/`)
3. Spawns one polling thread per endpoint
4. Each thread calls `eth_getBlockByNumber("latest")` at the configured rate
5. Measures RPC latency (request round-trip) and block lag (wall clock - block timestamp)
6. After the test duration, prints a summary table with averages and sync ETA

The Avalanche script additionally injects PoA/extraData middleware to handle the non-standard `extraData` length returned by AvalancheGo nodes.

## Use Cases

- **Verify nodes are synced** - block lag should be < 15s for Ethereum, < 5s for Avalanche
- **Compare endpoint performance** - latency differences across providers, regions, or instance types
- **Monitor initial sync progress** - ETA estimation shows how long until block lag reaches zero (or target threshold)
- **Validate after deployments** - quick smoke test after Ansible playbook runs
- **Compare public vs private endpoints** - add Infura/Alchemy alongside your own nodes
- **Monitor Avalanche subnets/L1s** - same tool works for any Avalanche-based network
