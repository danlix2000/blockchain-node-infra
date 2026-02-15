# JSON-RPC Load Testing

Load test Ethereum JSON-RPC endpoints using [Paradigm's flood](https://github.com/paradigmxyz/flood) via Docker.

Includes a Python runner (`flood_runner.py`) that automates test execution across multiple nodes with configurable suites for full and archive node types, and generates CSV + Markdown summary reports.

## Prerequisites

- Docker
- Python 3.8+
- Network access to the RPC endpoint(s)

Pull the flood image:

```bash
docker pull ghcr.io/paradigmxyz/flood:0.3.1
```

## Available Tests

```
docker run --rm ghcr.io/paradigmxyz/flood:0.3.1 ls
```

**Single load tests:**

| Test | Category | Full | Archive | Description |
|------|----------|:----:|:-------:|-------------|
| `eth_getBlockByNumber` | Block | Y | Y | Fetch block by number |
| `eth_getBalance` | State | Y | Y | Account balance lookup |
| `eth_getCode` | State | Y | Y | Contract bytecode |
| `eth_getStorageAt` | State | Y | Y | Contract storage slot |
| `eth_getTransactionCount` | State | Y | Y | Account nonce |
| `eth_call` | Execution | Y | Y | Simulate contract call |
| `eth_feeHistory` | Fee | Y | | Fee history data |
| `eth_getTransactionByHash` | Transaction | Y | | Fetch tx by hash |
| `eth_getTransactionReceipt` | Transaction | Y | | Fetch tx receipt |
| `eth_getLogs` | Logs | Y | Y | Query event logs |
| `trace_block` | Trace | | Y | Trace all txs in a block |
| `trace_transaction` | Trace | | Y | Trace a single tx |
| `trace_replayBlockTransactions` | Trace | | Y | Replay block txs |
| `trace_replayBlockTransactionsStateDiff` | Trace | | Y | Replay block - state diff |
| `trace_replayBlockTransactionsVmTrace` | Trace | | Y | Replay block - VM trace |
| `trace_replayTransaction` | Trace | | Y | Replay single tx |
| `trace_replayTransactionStateDiff` | Trace | | Y | Replay tx - state diff |
| `trace_replayTransactionVmTrace` | Trace | | Y | Replay tx - VM trace |

**Multi load tests:**

| Test | Description |
|------|-------------|
| `all` | Runs all single load tests sequentially |

## Quick Start

### 1. Configure nodes

Edit `nodes.json` with your endpoints:

```json
{
    "nodes": [
        {
            "name": "erigon-full-mainnet",
            "kind": "full",
            "spec": "erigon=http://10.0.1.50:8545"
        },
        {
            "name": "erigon-archive-mainnet",
            "kind": "archive",
            "spec": "erigon_archive=http://10.0.1.100:8545"
        }
    ]
}
```

### 2. Run tests

```bash
cd tools/load-test

# Run all nodes with all matching suites
python3 flood_runner.py --report

# Run only full node tests
python3 flood_runner.py --kinds full --report

# Run only archive node tests
python3 flood_runner.py --kinds archive --report
```

### 3. View results

```
flood_out/
  session_20250212_143000/
    summary.csv                  # All results in CSV
    summary.md                   # Markdown table
    erigon-full-mainnet/
      eth_getBlockByNumber/
        summary.txt              # Console output
        report.html              # Visual report (if --report)
      eth_call/
        ...
    erigon-archive-mainnet/
      trace_block/
        ...
```

## Basic Usage (flood directly)

These commands run flood directly via Docker - useful for quick one-off tests before using the runner.

### Single node

```bash
# Test eth_getBlockByNumber at 100 rps for 30 seconds
docker run --rm ghcr.io/paradigmxyz/flood:0.3.1 \
  eth_getBlockByNumber \
  erigon=http://10.0.1.50:8545 \
  --rates 50 100 200 \
  --duration 30

# Test eth_call at lower rates
docker run --rm ghcr.io/paradigmxyz/flood:0.3.1 \
  eth_call \
  erigon=http://10.0.1.50:8545 \
  --rates 10 25 50 100 \
  --duration 30
```

### Compare multiple nodes

```bash
# Compare Erigon vs Reth on the same test
docker run --rm ghcr.io/paradigmxyz/flood:0.3.1 \
  eth_getBlockByNumber \
  erigon=http://10.0.1.50:8545 \
  reth=http://10.0.1.60:8545 \
  --rates 50 100 200 400 \
  --duration 30
```

### Target local node from Docker

When running flood in Docker against a node on the same host, use `--network host`:

```bash
docker run --rm --network host ghcr.io/paradigmxyz/flood:0.3.1 \
  eth_getBlockByNumber \
  erigon=http://127.0.0.1:8545 \
  --rates 50 100 200 \
  --duration 30
```

### Save results and generate report

```bash
mkdir -p /tmp/flood_results

# Run test with output directory
docker run --rm \
  -v /tmp/flood_results:/out \
  ghcr.io/paradigmxyz/flood:0.3.1 \
  eth_getBlockByNumber \
  erigon=http://10.0.1.50:8545 \
  --rates 50 100 200 \
  --duration 30 \
  --output /out

# Print saved results
docker run --rm \
  -v /tmp/flood_results:/out \
  ghcr.io/paradigmxyz/flood:0.3.1 \
  print /out --metrics success throughput p90 p99

# Generate HTML report
docker run --rm \
  -v /tmp/flood_results:/out \
  ghcr.io/paradigmxyz/flood:0.3.1 \
  report /out
```

### Run all tests

```bash
# Runs every single load test sequentially
docker run --rm ghcr.io/paradigmxyz/flood:0.3.1 \
  all \
  erigon=http://10.0.1.50:8545 \
  --rates 10 25 50 \
  --duration 30
```

### Equality testing

Verify that multiple nodes return identical responses (correctness, not performance). Useful for comparing clients after upgrades or across different implementations:

```bash
# Compare Erigon vs Reth responses for correctness
docker run --rm ghcr.io/paradigmxyz/flood:0.3.1 \
  eth_getBlockByNumber \
  erigon=http://10.0.1.50:8545 \
  reth=http://10.0.1.60:8545 \
  --equality

# Compare all methods across clients
docker run --rm ghcr.io/paradigmxyz/flood:0.3.1 \
  all \
  erigon=http://10.0.1.50:8545 \
  reth=http://10.0.1.60:8545 \
  --equality
```

### Dry run

Preview what tests will be constructed without executing them:

```bash
docker run --rm ghcr.io/paradigmxyz/flood:0.3.1 \
  eth_getBlockByNumber \
  erigon=http://10.0.1.50:8545 \
  --rates 50 100 200 \
  --dry
```

### Reproducible tests

Use `--seed` for consistent random sample selection across runs:

```bash
docker run --rm ghcr.io/paradigmxyz/flood:0.3.1 \
  eth_getBlockByNumber \
  erigon=http://10.0.1.50:8545 \
  --rates 50 100 200 \
  --seed 42
```

### Remote node syntax

Flood supports built-in remote execution via SSH. Instead of running flood locally and pointing to a remote URL, flood can SSH to the remote host and run the test there (lower latency, more accurate results). Requires flood installed on the remote machine (not Docker).

```bash
# Run flood remotely via SSH (flood must be installed on remote host)
flood eth_getBlockByNumber erigon=ubuntu@10.0.1.50:localhost:8545

# With a display name
flood eth_getBlockByNumber erigon_mainnet=ubuntu@10.0.1.50:localhost:8545

# Compare two remote nodes
flood eth_getBlockByNumber \
  erigon=ubuntu@10.0.1.50:localhost:8545 \
  reth=ubuntu@10.0.1.60:localhost:8545 \
  --rates 50 100 200
```

> **Note:** Remote mode requires flood installed natively on the target hosts (not via Docker). For Docker-based testing, use the runner with `--network host` instead.

## Runner: flood_runner.py

The Python runner automates flood execution across multiple nodes using JSON configuration.

### How it works

1. Reads `nodes.json` for endpoint definitions (name, kind, RPC URL)
2. Reads `suites.json` for test definitions per node kind (full/archive)
3. For each node, runs all tests in the matching suite
4. Collects results into `summary.csv` and `summary.md`
5. Optionally generates HTML reports per test

### Command reference

```
python3 flood_runner.py [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--nodes` | `nodes.json` | Path to nodes config file |
| `--suites` | `suites.json` | Path to test suites config file |
| `--out` | `flood_out` | Output directory for results |
| `--image` | `ghcr.io/paradigmxyz/flood:0.3.1` | Flood Docker image |
| `--network` | (none) | Docker network mode (`host` for localhost) |
| `--kinds` | (all) | Comma-separated filter: `full`, `archive`, or `full,archive` |
| `--node` | (all) | Comma-separated node names to run (from `nodes.json`) |
| `--tests` | (all) | Comma-separated test names to run (from `suites.json`) |
| `--report` | false | Generate HTML report after each test |
| `--seed` | (random) | Fixed random seed for reproducible tests |
| `--dry` | false | Preview tests without running them |

### Run examples

**All nodes, all suites:**

```bash
python3 flood_runner.py --report
```

**Full nodes only:**

```bash
python3 flood_runner.py --kinds full --report
```

**Archive nodes only:**

```bash
python3 flood_runner.py --kinds archive --report
```

**Single node only** (by name from `nodes.json`):

```bash
python3 flood_runner.py --node erigon-sepolia-sea --report
```

**Specific test only** (run one test across all nodes):

```bash
python3 flood_runner.py --tests eth_getBlockByNumber --report
```

**Single test on a single node:**

```bash
python3 flood_runner.py --node erigon-sepolia-sea --tests eth_getBlockByNumber --report
```

**Multiple specific tests:**

```bash
python3 flood_runner.py --tests eth_getBlockByNumber,eth_call,eth_getLogs --report
```

**Multiple specific nodes:**

```bash
python3 flood_runner.py --node erigon-sepolia-sea,reth-archive-sv --report
```

**Combine all filters** (archive suite, one node, two tests):

```bash
python3 flood_runner.py --kinds archive --node reth-archive-sv --tests trace_block,trace_transaction --report
```

**Target localhost endpoints (node on same host as Docker):**

```bash
python3 flood_runner.py --network host --report
```

**Custom output directory:**

```bash
python3 flood_runner.py --out /data/loadtest_results --report
```

**Dry run** (preview what tests will execute without running them):

```bash
python3 flood_runner.py --dry
```

**Reproducible tests** (fixed seed for consistent random sample selection):

```bash
python3 flood_runner.py --seed 42 --report
```

**Custom flood image version:**

```bash
python3 flood_runner.py --image ghcr.io/paradigmxyz/flood:latest --report
```

## Configuration

### nodes.json

Defines the RPC endpoints to test. Each node has a name, kind (determines which suite runs), and a flood-format spec.

```json
{
    "nodes": [
        {
            "name": "erigon-full-mainnet",
            "kind": "full",
            "spec": "erigon=http://10.0.1.50:8545"
        },
        {
            "name": "reth-archive-mainnet",
            "kind": "archive",
            "spec": "reth=http://10.0.1.60:8545"
        }
    ]
}
```

| Field | Description |
|-------|-------------|
| `name` | Unique label for this node (used in output directory and reports) |
| `kind` | `full` or `archive` - selects the matching suite from `suites.json` |
| `spec` | Flood node spec format: `label=http://host:port` |

**Node spec format:** `label=url` or just `url`. The label before `=` is a display name used in flood's output tables. It can be anything descriptive (e.g. `erigon`, `reth`, `geth`, `erigon_archive`). The URL can be `http://host:port` or bare `host:port`.

**Multiple nodes example** (compare clients):

```json
{
    "nodes": [
        {
            "name": "erigon-full-mainnet",
            "kind": "full",
            "spec": "erigon=http://10.0.1.50:8545"
        },
        {
            "name": "reth-full-mainnet",
            "kind": "full",
            "spec": "reth=http://10.0.1.60:8545"
        },
        {
            "name": "geth-full-mainnet",
            "kind": "full",
            "spec": "geth=http://10.0.1.70:8545"
        },
        {
            "name": "erigon-archive-mainnet",
            "kind": "archive",
            "spec": "erigon=http://10.0.1.100:8545"
        },
        {
            "name": "reth-archive-mainnet",
            "kind": "archive",
            "spec": "reth=http://10.0.1.110:8545"
        }
    ]
}
```

### suites.json

Defines test configurations per node kind. Each suite has common defaults and a list of tests with rate ladders.

**Structure:**

```json
{
    "suites": {
        "full": {
            "common": { ... },
            "tests": [ ... ]
        },
        "archive": {
            "common": { ... },
            "tests": [ ... ]
        }
    }
}
```

**Common settings** (apply to all tests in the suite unless overridden per-test):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `duration` | int | `30` | Seconds to run at each rate step |
| `metrics` | list | `["success", "throughput", "p90"]` | Metrics to collect |
| `vegeta_args` | string | (none) | Extra args passed to the Vegeta load generator |
| `deep_check` | bool | `false` | Validate response content (slower but catches errors) |

**Per-test fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `test` | string | Yes | Flood test name (from `flood ls`) |
| `rates` | list[int] | Yes | Request rates (rps) to test - the rate ladder |
| `duration` | int | No | Override common duration for this test |
| `metrics` | list | No | Override common metrics for this test |
| `vegeta_args` | string | No | Override common vegeta_args for this test |
| `deep_check` | bool | No | Override common deep_check for this test |

## Rate Ladders

Rate ladders define the request-per-second (rps) steps that flood tests at. Each step runs for `duration` seconds. The ladder reveals where a node starts degrading.

### Default ladders

**Full node suite** (45s per step, 5s timeout):

| Test | Rates (rps) | Rationale |
|------|-------------|-----------|
| `eth_getBlockByNumber` | 50, 100, 200, 400, 800 | Lightweight - push high |
| `eth_getBalance` | 50, 100, 200, 400, 800 | Simple state read |
| `eth_getCode` | 50, 100, 200, 400, 800 | Simple state read |
| `eth_getStorageAt` | 50, 100, 200, 400, 800 | Simple state read |
| `eth_getTransactionCount` | 50, 100, 200, 400, 800 | Simple state read |
| `eth_call` | 20, 50, 100, 200, 400 | Requires EVM execution |
| `eth_feeHistory` | 20, 50, 100, 200, 400 | Scans multiple blocks |
| `eth_getTransactionByHash` | 25, 50, 100, 200, 400 | DB lookup |
| `eth_getTransactionReceipt` | 25, 50, 100, 200, 400 | DB lookup + logs |
| `eth_getLogs` | 5, 10, 25, 50, 100 | Block range scan - heavy |

**Archive node suite** (60s per step, 15s timeout, deep_check enabled):

| Test | Rates (rps) | Rationale |
|------|-------------|-----------|
| `eth_getBlockByNumber` | 50, 100, 200, 400 | Baseline comparison |
| `eth_getBalance` | 25, 50, 100, 200 | Historical state lookup |
| `eth_getStorageAt` | 25, 50, 100, 200 | Historical state lookup |
| `eth_call` | 10, 25, 50, 100 | Historical EVM execution |
| `eth_getLogs` | 2, 5, 10, 25 | Large range scans |
| `trace_block` | 1, 2, 5, 10 | Full block trace - expensive |
| `trace_transaction` | 1, 2, 5, 10 | Single tx trace |
| `trace_replayBlockTransactions` | 1, 2, 5 | Re-execute full block |
| `trace_replayTransaction` | 1, 2, 5, 10 | Re-execute single tx |
| `trace_replay*StateDiff` | 1, 2, 5 (block) / 1, 2, 5, 10 (tx) | State changes per call |
| `trace_replay*VmTrace` | 1, 2, 5 (block) / 1, 2, 5, 10 (tx) | Full VM execution trace |

### Customizing rates

Edit `suites.json` to adjust. Guidelines:

- **Start low:** Begin at a rate where 100% success is expected
- **Double or halve:** Use geometric steps (e.g. 10, 25, 50, 100) to find the cliff
- **Trace tests are expensive:** Keep rates low (1-10 rps) - they replay full execution
- **`eth_getLogs` scales with block range:** flood uses varying ranges, so keep rates moderate
- **Longer duration = more stable results:** 30s minimum, 60s for traces

## Metrics

The runner collects four metrics per rate step:

| Metric | Description | Good Value |
|--------|-------------|------------|
| `success` | Percentage of requests that returned a valid response | 100% |
| `throughput` | Actual requests per second achieved | Close to target rate |
| `p90` | 90th percentile response time (seconds) | < 1s for reads, < 5s for traces |
| `p99` | 99th percentile response time (seconds) | < 2s for reads, < 15s for traces |

### Reading the results

**Healthy node at 200 rps:**
```
success: 100%  |  throughput: 200 rps  |  p90: 0.05s  |  p99: 0.12s
```

**Node at capacity (400 rps target):**
```
success: 95%   |  throughput: 380 rps  |  p90: 1.2s   |  p99: 3.5s
```

**Node overloaded (800 rps target):**
```
success: 60%   |  throughput: 480 rps  |  p90: 5.0s   |  p99: timeout
```

Look for:
- **Success cliff:** The rate where success drops below 99% is the practical capacity
- **Latency cliff:** The rate where p90 exceeds your SLA threshold
- **Throughput plateau:** When throughput stops increasing despite higher target rate

## Output Files

Each session creates a timestamped directory inside `flood_out/`:

```
flood_out/session_20250212_143000/
  summary.csv             # All results across all nodes/tests (machine-readable)
  summary.md              # Same data as markdown table (paste into PRs, docs)
  erigon-full-mainnet/    # One directory per node
    eth_getBlockByNumber/
      summary.txt         # Flood console output (rate tables)
      report.html         # Visual charts (if --report flag used)
      test.json           # Test parameters (rates, duration, seed)
      results.json        # Raw metrics per rate step
      figures/            # PNG charts (if --report flag used)
    eth_call/
      ...
  erigon-archive-mainnet/
    trace_block/
      ...
```

### Reading the output

**1. Quick overview - `summary.md`:**

Start here. Open `flood_out/session_*/summary.md` in any markdown viewer or paste into a GitHub issue/PR. Shows all nodes, tests, and rates in a single table.

```bash
cat flood_out/session_*/summary.md
```

Failed tests show `FAILED` in the success column - the runner continues past failures instead of crashing.

**2. Visual report - `report.html`:**

Generated when using `--report`. Open in a browser for charts showing throughput, latency, and success rate curves per test.

```bash
# Open the report for a specific test
xdg-open flood_out/session_*/erigon-full-mainnet/eth_getBlockByNumber/report.html

# Or on macOS
open flood_out/session_*/erigon-full-mainnet/eth_getBlockByNumber/report.html
```

Each report includes:
- Throughput vs target rate chart
- Latency distribution (p50, p90, p99) per rate step
- Success rate curve

**3. Console tables - `summary.txt`:**

Flood's raw console output with rate-by-rate tables. Useful for quick terminal review.

```bash
cat flood_out/session_*/erigon-full-mainnet/eth_getBlockByNumber/summary.txt
```

**4. Machine-readable - `summary.csv`:**

Import into spreadsheets, Grafana, or scripts for analysis.

```bash
# View CSV
column -t -s, flood_out/session_*/summary.csv

# Filter for a specific node
grep erigon-full flood_out/session_*/summary.csv

# Find the rate where success drops below 100%
awk -F, '$6 != "100.0" && $6 != "success_pct" {print $2, $4, $5, $6}' flood_out/session_*/summary.csv
```

**5. Raw data - `results.json` / `test.json`:**

`test.json` contains the test parameters (rates, duration, node URL, seed). `results.json` contains the raw metrics flood collected at each rate step - useful for custom analysis or feeding into monitoring dashboards.

### summary.csv columns

| Column | Description |
|--------|-------------|
| `session` | Timestamp ID (e.g. `20250212_143000`) |
| `node` | Node name from `nodes.json` |
| `kind` | `full` or `archive` |
| `test` | Flood test name |
| `rate_rps` | Target request rate |
| `success_pct` | Success percentage at this rate (`FAILED` if test errored) |
| `throughput_rps` | Actual throughput achieved |
| `p90_s` | p90 latency in seconds |
| `p99_s` | p99 latency in seconds |
| `output_dir` | Path to detailed results for this test |

## Remote Execution

For accurate results, run flood close to the node to minimize network latency. SSH into the node host or a machine in the same network:

```bash
# Copy load-test files to the remote host
scp -r tools/load-test/ ubuntu@10.0.1.50:/tmp/load-test/

# SSH in and run
ssh ubuntu@10.0.1.50
cd /tmp/load-test
docker pull ghcr.io/paradigmxyz/flood:0.3.1

# Test local node (use --network host since node is on same host)
python3 flood_runner.py --network host --report

# Copy results back
exit
scp -r ubuntu@10.0.1.50:/tmp/load-test/flood_out/ ./results/
```

## Troubleshooting

**Docker cannot reach the node:**
- Use `--network host` when testing localhost endpoints
- Verify the RPC port is accessible: `curl -s http://10.0.1.50:8545 -X POST -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'`
- Check firewall rules (UFW on Latitude BM, Security Groups on AWS)

**All requests fail (0% success):**
- Node may not have the required RPC APIs enabled
- For trace tests: ensure the node has `trace` API enabled and is an archive node
- Check node sync status - a syncing node will return errors

**Timeouts on trace tests:**
- Trace operations are expensive - increase timeout: edit `vegeta_args` in `suites.json` to `-timeout 30s`
- Reduce rates to 1-2 rps
- Verify the node has enough resources (CPU, RAM, disk IOPS)

**Permission denied on output directory:**
- Docker needs write access to the output mount: `mkdir -p flood_out && chmod 777 flood_out`

**flood image not found:**
- Pull the image first: `docker pull ghcr.io/paradigmxyz/flood:0.3.1`
- Or use latest: `--image ghcr.io/paradigmxyz/flood:latest`
