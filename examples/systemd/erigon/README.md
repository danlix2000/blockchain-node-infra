# Erigon (Systemd Service)

Reference systemd service file for running [Erigon v3](https://github.com/erigontech/erigon) as a native binary with built-in Caplin consensus client.

> **Note:** Production deployments use Ansible (`ansible/roles/erigon/`). This is a standalone reference for manual setups.

## Architecture

Erigon v3 includes **Caplin**, a built-in consensus layer client. Unlike Docker-based Reth+Lighthouse or Geth+Prysm setups, Erigon runs as a single binary - no separate CL container needed.

## Prerequisites

- Go >= 1.25 (for building from source)
- Linux with systemd
- Dedicated service user (`ethereum`, UID 2000)
- Data disk mounted at `/data`

## Build from Source

Build as the `ethereum` service user to avoid shared library permission issues:

```bash
# 1. Create service user (if not already created)
sudo useradd -r -u 2000 -s /usr/sbin/nologin ethereum

# 2. Create build directory owned by service user
sudo mkdir -p /opt/erigon
sudo chown ethereum:ethereum /opt/erigon

# 3. Clone and build as service user
sudo -u ethereum git clone --branch v3.3.7 --single-branch https://github.com/erigontech/erigon.git /opt/erigon
sudo -u ethereum bash -c 'cd /opt/erigon && PATH=/usr/local/go/bin:$PATH make erigon'

# 4. Verify
/opt/erigon/build/bin/erigon --version
```

> **Important:** The binary links to `libsilkworm_capi.so` in `build/bin/`. Building and running as the same user ensures the dynamic linker resolves the shared library correctly. The systemd service uses `LD_LIBRARY_PATH` as a safety net.

## Install Service

```bash
# 1. Create service user (skip if done above)
sudo useradd -r -u 2000 -s /usr/sbin/nologin ethereum

# 2. Prepare data directory
sudo mkdir -p /data/erigon
sudo chown ethereum:ethereum /data/erigon

# 3. Generate JWT secret (if using external CL)
openssl rand -hex 32 | sudo tee /data/erigon/jwt.hex > /dev/null
sudo chown ethereum:ethereum /data/erigon/jwt.hex

# 4. Install service file
sudo cp erigon.service /etc/systemd/system/erigon.service

# 5. Edit the service file for your setup (full vs archive, network, etc.)
sudo systemctl edit --full erigon.service

# 6. Enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now erigon.service

# 7. Check status and logs
sudo systemctl status erigon
sudo journalctl -u erigon -f
```

## Node Modes

### Full Node (Default)

No `--prune.mode` flag - Erigon defaults to full mode.

### Archive Node

Add these flags to ExecStart:

```
--prune.mode=archive \
--experimental.commitment-history \
```

## Ports

| Port | Protocol | Description |
|------|----------|-------------|
| 30303 | TCP/UDP | P2P discovery and sync |
| 4000 | UDP | Caplin CL discovery |
| 4001 | TCP | Caplin CL discovery TCP |
| 8545 | TCP | HTTP JSON-RPC |
| 8551 | TCP | Engine API (internal) |
| 42069 | TCP/UDP | BitTorrent (snapshot download) |
| 6060 | TCP | Metrics (Prometheus) |

## Upgrading

```bash
sudo systemctl stop erigon
sudo -u ethereum bash -c 'cd /opt/erigon && git fetch --tags && git checkout <new-version> && PATH=/usr/local/go/bin:$PATH make erigon'
sudo systemctl start erigon
```

The Ansible role handles this automatically - change `erigon_version` in group vars and re-run the playbook.
