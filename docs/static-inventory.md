# Static Inventory Guide

How to deploy Ethereum nodes using a static Ansible inventory (without Terraform).

This is useful when:
- The server is not managed by Terraform
- You want to test the Ansible role quickly
- You're migrating an existing manually-deployed node

## Create a Static Inventory File

Create a YAML inventory file in `ansible/inventory/`. The host must be placed in the correct Ansible groups for the role and network-specific variables to apply.

### Required Groups

**Erigon nodes (binary build):**

| Group | Purpose | Required? |
|-------|---------|-----------|
| `erigon` | Targets the Erigon playbook | Yes - all Erigon nodes |
| `network_mainnet` or `network_sepolia` | Network-specific group_vars | Yes - chain selection |
| `platform_latitude` or `platform_aws` | Platform-specific overrides | Yes - `ansible_user`, firewall |
| `node_archive` | Archive overrides (prune.mode, commitment-history) | Only for archive nodes |

> **Note:** Full nodes do not need a `node_full` group - Erigon defaults to full mode. Only archive nodes need the `node_archive` group to apply `--prune.mode=archive` + `--experimental.commitment-history`.

**Docker nodes (Reth+Lighthouse, Geth+Prysm):**

| Group | Purpose | Required? |
|-------|---------|-----------|
| `ethereum` | Targets the Docker ethereum playbook | Yes - all Docker nodes |
| `network_mainnet` or `network_sepolia` | Network-specific group_vars | Yes - chain selection |
| `platform_latitude` or `platform_aws` | Platform-specific overrides | Yes - `ansible_user`, firewall |

Docker nodes also require these **per-host variables**:

| Variable | Values | Purpose |
|----------|--------|---------|
| `execution_client` | `reth` or `geth` | Selects Docker Compose template |
| `consensus_client` | `lighthouse` or `prysm` | Selects Docker Compose template |
| `node_type` | `full` or `archive` | Controls pruning flags |

> **Note:** Only two client pairs are supported: `reth`+`lighthouse` and `geth`+`prysm`. Other combinations will fail validation.

---

## Erigon Examples

### Erigon Full Node - Mainnet (Latitude BM)

```yaml
# ansible/inventory/ethereum_mainnet_hosts.yml
all:
  children:
    erigon:
      hosts:
        mainnet-erigon-full:
          ansible_host: 192.168.1.50
          data_device: /dev/md127
    network_mainnet:
      hosts:
        mainnet-erigon-full: {}
    platform_latitude:
      hosts:
        mainnet-erigon-full: {}
```

No `node_archive` group - Erigon runs in full mode by default.

### Erigon Full Node - Mainnet (AWS)

```yaml
# ansible/inventory/ethereum_mainnet_hosts.yml
all:
  children:
    erigon:
      hosts:
        mainnet-erigon-full:
          ansible_host: 54.123.45.67
          data_device: /dev/nvme1n1
    network_mainnet:
      hosts:
        mainnet-erigon-full: {}
    platform_aws:
      hosts:
        mainnet-erigon-full: {}
```

AWS uses `/dev/nvme1n1` (EBS volume). No `platform_latitude` - UFW firewall stays disabled (AWS uses Security Groups).

### Erigon Archive Node - Mainnet (AWS)

```yaml
# ansible/inventory/ethereum_mainnet_manual.yml
all:
  children:
    erigon:
      hosts:
        mainnet-erigon-arch:
          ansible_host: 54.123.45.67
          data_device: /dev/nvme1n1
    node_archive:
      hosts:
        mainnet-erigon-arch: {}
    network_mainnet:
      hosts:
        mainnet-erigon-arch: {}
    platform_aws:
      hosts:
        mainnet-erigon-arch: {}
```

### Erigon Archive Node - Sepolia (Latitude BM)

```yaml
# ansible/inventory/ethereum_sepolia_hosts.yml
all:
  children:
    erigon:
      hosts:
        sepolia-erigon-arch:
          ansible_host: 86.109.2.85
          data_device: /dev/md127
          external_ip: 86.109.2.85  # Optional: set --nat=extip:
    node_archive:
      hosts:
        sepolia-erigon-arch: {}     # Applies --prune.mode=archive + --experimental.commitment-history
    network_sepolia:
      hosts:
        sepolia-erigon-arch: {}
    platform_latitude:
      hosts:
        sepolia-erigon-arch: {}
```

### Erigon Archive Node - Sepolia (AWS)

```yaml
# ansible/inventory/ethereum_sepolia_manual.yml
all:
  children:
    erigon:
      hosts:
        sepolia-erigon-arch:
          ansible_host: 54.200.10.20
          data_device: /dev/nvme1n1
    node_archive:
      hosts:
        sepolia-erigon-arch: {}
    network_sepolia:
      hosts:
        sepolia-erigon-arch: {}
    platform_aws:
      hosts:
        sepolia-erigon-arch: {}
```

### Multiple Erigon Nodes (Full + Archive)

```yaml
# ansible/inventory/multi_node_hosts.yml
all:
  children:
    erigon:
      hosts:
        mainnet-erigon-full:
          ansible_host: 192.168.1.50
          data_device: /dev/md127
        mainnet-erigon-arch:
          ansible_host: 192.168.1.100
          data_device: /dev/md127
        sepolia-erigon-arch:
          ansible_host: 86.109.2.85
          data_device: /dev/md127
    node_archive:
      hosts:
        mainnet-erigon-arch: {}     # Archive mode
        sepolia-erigon-arch: {}     # Archive mode
    network_mainnet:
      hosts:
        mainnet-erigon-full: {}
        mainnet-erigon-arch: {}
    network_sepolia:
      hosts:
        sepolia-erigon-arch: {}
    platform_latitude:
      hosts:
        mainnet-erigon-full: {}
        mainnet-erigon-arch: {}
        sepolia-erigon-arch: {}
```

---

## Docker Examples

### Reth+Lighthouse Archive Node - Mainnet (AWS)

```yaml
# ansible/inventory/ethereum_mainnet_hosts.yml
all:
  children:
    ethereum:
      hosts:
        mainnet-reth-archive:
          ansible_host: 54.123.45.67
          data_device: /dev/nvme1n1
          node_type: archive
          execution_client: reth
          consensus_client: lighthouse
    network_mainnet:
      hosts:
        mainnet-reth-archive: {}
    platform_aws:
      hosts:
        mainnet-reth-archive: {}
```

Archive mode: Reth runs without `--full` flag (stores everything). Lighthouse runs with `--reconstruct-historic-states`.

### Geth+Prysm Full Node - Mainnet (AWS)

```yaml
# ansible/inventory/ethereum_mainnet_hosts.yml
all:
  children:
    ethereum:
      hosts:
        mainnet-geth-full:
          ansible_host: 54.200.10.20
          data_device: /dev/nvme1n1
          node_type: full
          execution_client: geth
          consensus_client: prysm
    network_mainnet:
      hosts:
        mainnet-geth-full: {}
    platform_aws:
      hosts:
        mainnet-geth-full: {}
```

### Reth+Lighthouse Full Node - Sepolia (AWS)

```yaml
# ansible/inventory/ethereum_sepolia_hosts.yml
all:
  children:
    ethereum:
      hosts:
        sepolia-reth-full:
          ansible_host: 54.100.20.30
          data_device: /dev/nvme1n1
          node_type: full
          execution_client: reth
          consensus_client: lighthouse
    network_sepolia:
      hosts:
        sepolia-reth-full: {}
    platform_aws:
      hosts:
        sepolia-reth-full: {}
```

### Geth+Prysm Full Node - Sepolia (Latitude BM)

```yaml
# ansible/inventory/ethereum_sepolia_hosts.yml
all:
  children:
    ethereum:
      hosts:
        sepolia-geth-full:
          ansible_host: 86.109.2.90
          data_device: /dev/md127
          node_type: full
          execution_client: geth
          consensus_client: prysm
    network_sepolia:
      hosts:
        sepolia-geth-full: {}
    platform_latitude:
      hosts:
        sepolia-geth-full: {}
```

### Multiple Docker Nodes (Mixed Clients)

```yaml
# ansible/inventory/ethereum_mainnet_hosts.yml
all:
  children:
    ethereum:
      hosts:
        mainnet-reth-archive:
          ansible_host: 54.123.45.67
          data_device: /dev/nvme1n1
          node_type: archive
          execution_client: reth
          consensus_client: lighthouse
        mainnet-geth-full:
          ansible_host: 54.200.10.20
          data_device: /dev/nvme1n1
          node_type: full
          execution_client: geth
          consensus_client: prysm
    network_mainnet:
      hosts:
        mainnet-reth-archive: {}
        mainnet-geth-full: {}
    platform_aws:
      hosts:
        mainnet-reth-archive: {}
        mainnet-geth-full: {}
```

---

## Deploy

All commands run from the `ansible/` directory:

```bash
cd ansible
export ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/your-key.pem
```

**Erigon nodes:**

```bash
# Test connectivity
ansible -i inventory/ethereum_mainnet_hosts.yml all -m ping

# RAID setup (Latitude BM with multiple disks only - skip for AWS and single-disk BM)
ansible-playbook -i inventory/ethereum_mainnet_hosts.yml playbooks/raid.yml

# Deploy Erigon (mainnet)
ansible-playbook -i inventory/ethereum_mainnet_hosts.yml playbooks/erigon.yml

# Deploy Erigon (Sepolia)
ansible-playbook -i inventory/ethereum_sepolia_hosts.yml playbooks/erigon.yml

# Dry run first
ansible-playbook -i inventory/ethereum_mainnet_hosts.yml playbooks/erigon.yml --check --diff

# Deploy specific node
ansible-playbook -i inventory/multi_node_hosts.yml playbooks/erigon.yml --limit mainnet-erigon-full
```

**Docker nodes (Reth+Lighthouse, Geth+Prysm):**

```bash
# Test connectivity
ansible -i inventory/ethereum_mainnet_hosts.yml all -m ping

# RAID setup (Latitude BM with multiple disks only - skip for AWS and single-disk BM)
ansible-playbook -i inventory/ethereum_mainnet_hosts.yml playbooks/raid.yml

# Deploy Docker nodes (mainnet)
ansible-playbook -i inventory/ethereum_mainnet_hosts.yml playbooks/ethereum.yml

# Deploy Docker nodes (Sepolia)
ansible-playbook -i inventory/ethereum_sepolia_hosts.yml playbooks/ethereum.yml

# Dry run first
ansible-playbook -i inventory/ethereum_mainnet_hosts.yml playbooks/ethereum.yml --check --diff

# Deploy specific node
ansible-playbook -i inventory/ethereum_mainnet_hosts.yml playbooks/ethereum.yml --limit mainnet-geth-full
```

## How Variables Resolve

### Erigon nodes

Ansible applies group_vars based on group membership. For a host in `erigon` + `node_archive` + `network_sepolia`:

1. `roles/erigon/defaults/main.yml` - role defaults (lowest priority)
2. `group_vars/erigon/main.yml` - base Erigon config (full mode, mainnet chain)
3. `group_vars/network_sepolia/main.yml` - Sepolia overrides (chain, RPC tuning)
4. `group_vars/node_archive/main.yml` - archive overrides (prune.mode, commitment-history)
5. Host vars in inventory file - per-host overrides (highest priority)

Alphabetical group precedence: `node_archive` > `network_sepolia` > `erigon`.

For a **full** node (no `node_archive` group), step 4 is skipped - Erigon uses its native full mode.

### Docker nodes

For a host in `ethereum` + `network_mainnet`:

1. `roles/ethereum/defaults/main.yml` - role defaults (lowest priority)
2. `group_vars/ethereum/main.yml` - client versions, images, ports, RPC config
3. `group_vars/network_mainnet/main.yml` - mainnet network (or `network_sepolia` for Sepolia checkpoint URL)
4. Host vars in inventory file - `execution_client`, `consensus_client`, `node_type` (highest priority)

The `execution_client` + `consensus_client` host vars select the Docker Compose template (`reth-lighthouse.yml.j2` or `geth-prysm.yml.j2`). The `node_type` controls pruning flags.

## Per-Host Overrides

You can override any variable at the host level in the inventory:

**Erigon:**
```yaml
erigon:
  hosts:
    my-node:
      ansible_host: 10.0.0.1
      data_device: /dev/nvme0n1
      external_ip: 203.0.113.10       # --nat=extip:
      erigon_torrent_download_rate: "1000mb"  # Override torrent speed
```

**Docker:**
```yaml
ethereum:
  hosts:
    my-node:
      ansible_host: 10.0.0.1
      data_device: /dev/nvme0n1
      node_type: archive
      execution_client: reth
      consensus_client: lighthouse
      external_ip: 203.0.113.10       # P2P external IP
      checkpoint_sync_url: ""         # Disable checkpoint sync (sync from genesis)
```

## Migrating to Terraform

When ready to manage the server with Terraform:

1. Create a Terraform stack (copy from `terraform/stacks/aws/ethereum/mainnet/` or `terraform/stacks/latitude/ethereum/mainnet/`)
2. Add the server to `nodes.tfvars` with its details (`latitude_id` for BM, instance config for AWS)
3. Run `terraform apply -var-file=nodes.tfvars` to import and generate dynamic inventory
4. Switch from the static inventory file to the auto-generated one
5. Delete the static inventory file
