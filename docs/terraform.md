# Terraform

Infrastructure provisioning for blockchain nodes. Designed for multi-cloud deployments.

## Directory Structure

```
terraform/
├── stacks/
│   ├── aws/
│   │   └── ethereum/
│   │       ├── mainnet/              # AWS Ethereum Mainnet
│   │       └── sepolia/              # AWS Ethereum Sepolia
│   └── latitude/
│       └── ethereum/
│           ├── mainnet/              # Latitude BM Ethereum Mainnet
│           └── sepolia/              # Latitude BM Ethereum Sepolia
└── modules/
    ├── network/                      # AWS VPC, subnets, security groups
    ├── compute/                      # AWS EC2, EBS, EIP
    └── compute-latitude/             # Latitude bare metal servers
```

### Directory Naming Convention

| Path | Description |
|------|-------------|
| `stacks/{platform}/{chain}/{network}/` | Platform + chain + network stack |

Each network has isolated Terraform state - deploying Sepolia won't affect Mainnet.

## Multi-Chain Architecture

Each chain has its own Terraform root with **isolated state**:

| Benefit | Description |
|---------|-------------|
| **Isolation** | Each chain has separate state - no blast radius |
| **Independent** | Deploy Ethereum without affecting Arbitrum |
| **Scalable** | Add new chains by copying template |
| **Team-friendly** | Different teams can own different chains |

## Modules

### Network Module

Creates the VPC infrastructure:

| Resource | Description |
|----------|-------------|
| VPC | Main VPC with DNS support |
| Subnet | Public subnet with IGW route for node deployment |
| Internet Gateway | Internet access |
| Security Groups | SSH (VPN whitelist), per-client P2P (execution, erigon, lighthouse, prysm), HAProxy (80/443 public) |

### Compute Module (AWS)

Creates AWS compute resources:

| Resource | Description |
|----------|-------------|
| EC2 Instance | Ubuntu 24.04, EBS-optimized, IMDSv2 required |
| EBS Volume | Encrypted data volume for blockchain data |
| Volume Attachment | Attaches data volume to instance |
| Elastic IP | Optional - stable public endpoint |
| IAM Instance Profile | Route 53 access for Certbot DNS-01 (HAProxy TLS), scoped to `route53_zone_id` when set |

### Compute-Latitude Module (Bare Metal)

Imports pre-ordered Latitude.sh bare metal servers into Terraform state:

| Resource | Description |
|----------|-------------|
| latitudesh_server | Pre-ordered bare metal server (imported via `latitude_id`) |

**Workflow:**
1. Order servers on Latitude.sh dashboard (select plan, site, Ubuntu 24.04 - **no RAID**, Ansible handles RAID setup)
2. Copy each server's ID (`sv_xxx`) into `nodes.tfvars` as `latitude_id`
3. `terraform apply` imports existing servers and creates Ansible inventory

Key differences from AWS:
- Servers are **pre-ordered** on dashboard, not created by Terraform
- No VPC, subnets, or security groups (direct public IPs)
- No EBS volumes (local NVMe/SATA drives with RAID-0 for performance)
- `lifecycle { ignore_changes = all }` prevents Terraform from modifying imported servers

Provider: `latitudesh/latitudesh` ~> 2.5.0
Auth: `export LATITUDESH_AUTH_TOKEN="your-token"`

## Remote State (HCP Terraform)

Use [HCP Terraform](https://app.terraform.io) (Terraform Cloud) for state management. Recommended for multi-cloud deployments.

### Setup HCP Terraform

1. Create account at [app.terraform.io](https://app.terraform.io)

2. Create organization and workspace

3. Generate API token: User Settings > Tokens > Create API token

4. Authenticate (choose one):

```bash
# Option A: Export API token (recommended for CI/CD)
export TF_TOKEN_app_terraform_io="your-api-token"

# Option B: Interactive login
terraform login
```

5. Configure backend:

```bash
cd terraform/stacks/aws/ethereum/mainnet
cp cloud.tf.example cloud.tf
# Edit cloud.tf with your organization and workspace
```

6. Initialize:

```bash
terraform init
```

### AWS Credentials

This repo uses **local execution** mode - Terraform runs on your machine, TF Cloud stores state only.

Set execution mode in TF Cloud: **Workspace > Settings > General > Execution Mode > Local**

Configure AWS credentials locally:

```bash
# Option A: Use AWS CLI profile (recommended)
aws configure

# Option B: Export credentials
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-1"
```

Verify credentials:

```bash
aws sts get-caller-identity
```

### Latitude.sh Credentials

For bare metal deployments on Latitude.sh:

```bash
# Latitude API token (from dashboard: Account > API Keys)
export LATITUDESH_AUTH_TOKEN="your-latitude-api-token"
```

Setup:
1. Create a project in the Latitude.sh dashboard
2. Order bare metal servers (select plan, site, Ubuntu 24.04 - no RAID, Ansible handles it)
3. Add your SSH key under Account > SSH Keys (note the key ID)
4. Copy the project ID and server IDs (`sv_xxx`) from the dashboard
5. Set `project_id` and `ssh_key_ids` in `terraform.tfvars`
6. Set `latitude_id` for each server in `nodes.tfvars`

## Configuration

### Required Variables

| Variable | Description |
|----------|-------------|
| `key_name` | EC2 key pair name (create in AWS Console) |
| `allowed_ssh_cidrs` | VPN/office IP CIDRs for SSH access |
| `nodes` | Map of nodes to deploy (see below) |

### Node Configuration

Define all nodes in `nodes.tfvars` (single source of truth):

```hcl
nodes = {
  full = {
    role                   = "ethereum"
    node_type              = "full"
    execution_client       = "geth"
    consensus_client       = "prysm"
    instance_type          = "m7i.2xlarge"   # 8 vCPU, 32GB RAM
    root_volume_size_gb    = 100
    data_volume_size_gb    = 2000            # 2TB for full node
    data_volume_iops       = 6000
    data_volume_throughput = 250
  }
  archive = {
    role                   = "ethereum"
    node_type              = "archive"
    execution_client       = "reth"
    consensus_client       = "lighthouse"
    instance_type          = "m7i.4xlarge"   # 16 vCPU, 64GB RAM
    root_volume_size_gb    = 100
    data_volume_size_gb    = 5000            # 5TB for archive
    data_volume_iops       = 10000
    data_volume_throughput = 500
  }
}
```

**Erigon nodes** use `role = "erigon"` for binary build (no Docker). Erigon defaults to full mode. For archive, set `node_type = "archive"` which applies `group_vars/node_archive/` overrides (`--prune.mode=archive` + `--experimental.commitment-history`):

```hcl
nodes = {
  # Erigon full node (default mode - no --prune.mode flag)
  erigon-full = {
    role                   = "erigon"     # Binary build (Ansible playbooks/erigon.yml)
    node_type              = "full"
    execution_client       = "erigon"
    consensus_client       = "caplin"     # Built-in CL (no separate beacon node)
    instance_type          = "m7i.2xlarge"
    root_volume_size_gb    = 100
    data_volume_size_gb    = 2000
    data_volume_iops       = 6000
    data_volume_throughput = 250
  }

  # Erigon archive node (--prune.mode=archive via group_vars/node_archive/)
  erigon-arch = {
    role                   = "erigon"
    node_type              = "archive"    # Applies group_vars/node_archive/ overrides
    execution_client       = "erigon"
    consensus_client       = "caplin"
    instance_type          = "m7i.4xlarge"
    root_volume_size_gb    = 100
    data_volume_size_gb    = 3000
    data_volume_iops       = 10000
    data_volume_throughput = 500
  }
}
```

**Client selection** is explicit per node. Defaults can be inferred from `node_type` if omitted.

| Node Attribute | Required | Default | Description |
|---------------|----------|---------|-------------|
| `role` | No | chain | Ansible role group (`ethereum` for Docker, `erigon` for binary) |
| `node_type` | No | derived | `full` or `archive` |
| `execution_client` | No | derived | `geth`, `reth`, `erigon` |
| `consensus_client` | No | derived | `lighthouse`, `prysm`, `caplin` |
| `instance_type` | Yes | - | EC2 instance type |
| `root_volume_size_gb` | Yes | - | Root volume size |
| `data_volume_size_gb` | Yes | - | Data volume size |
| `data_volume_type` | No | gp3 | EBS volume type |
| `data_volume_iops` | No | 3000 | IOPS for gp3 |
| `data_volume_throughput` | No | 125 | Throughput MB/s for gp3 |
| `subnet_index` | No | 0 | Index of subnet |
| `associate_eip` | No | false | Attach Elastic IP for stable endpoint |
| `domain` | No | empty | FQDN for Route 53 A record (e.g., `full.rpc.eth.example.com`) |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `aws_region` | us-east-1 | AWS region |
| `project_name` | blockchain | Resource name prefix |
| `route53_zone_id` | empty | Route 53 hosted zone ID (required if any node has a `domain`) |

See `terraform.tfvars.example` for all variables.

### P2P Security Groups

P2P ports are managed as per-client security groups. Each node receives only the SGs matching its `execution_client` and `consensus_client`:

| Security Group | Ports | Clients |
|----------------|-------|---------|
| `p2p-execution` | 30303/tcp, 30303/udp | All (geth, reth, erigon) |
| `p2p-erigon` | 30304/tcp+udp, 42069/tcp+udp, 4000/udp, 4001/tcp | erigon+caplin |
| `p2p-lighthouse` | 9000/tcp, 9000/udp, 9001/udp | lighthouse |
| `p2p-prysm` | 13000/tcp, 12000/udp | prysm |

Example SG assignment:
- **geth + prysm** node: `ssh`, `haproxy`, `p2p-execution`, `p2p-prysm`
- **reth + lighthouse** node: `ssh`, `haproxy`, `p2p-execution`, `p2p-lighthouse`
- **erigon + caplin** node: `ssh`, `haproxy`, `p2p-execution`, `p2p-erigon`

Use `p2p_allowed_cidrs` to restrict source CIDRs (default: `0.0.0.0/0`).

## Ansible Inventory (Auto-Generated)

Terraform automatically generates the Ansible inventory plugin configuration at `ansible/inventory/`. This file tells Ansible how to read `ansible_host` resources from Terraform state.

**How it works:**
1. Terraform registers hosts in state via the `ansible_host` resource
2. `terraform apply` generates `ansible/inventory/{chain}_{network}_{platform}_terraform_state.yml`
3. Ansible reads hosts at runtime using the `cloud.terraform.terraform_provider` plugin (runs `terraform show` locally)

```bash
# Requires: terraform login (or TF_TOKEN_app_terraform_io)
cd ansible
ansible-inventory -i inventory/ethereum_mainnet_aws_terraform_state.yml --list
ansible-inventory -i inventory/ethereum_sepolia_latitude_terraform_state.yml --list
```

Auto-generated inventory files:
- `ethereum_mainnet_aws_terraform_state.yml`
- `ethereum_mainnet_latitude_terraform_state.yml`
- `ethereum_sepolia_aws_terraform_state.yml`
- `ethereum_sepolia_latitude_terraform_state.yml`

The inventory includes host variables and groups (chain, network, node type, clients) so you can target:

```bash
# Docker nodes (Reth+Lighthouse, Geth+Prysm)
ansible-playbook -i inventory/ethereum_mainnet_aws_terraform_state.yml playbooks/ethereum.yml --limit node_archive

# Erigon nodes (Erigon+Caplin, binary build)
ansible-playbook -i inventory/ethereum_mainnet_latitude_terraform_state.yml playbooks/erigon.yml --limit node_archive

# Sepolia Erigon nodes (Erigon+Caplin)
ansible-playbook -i inventory/ethereum_sepolia_latitude_terraform_state.yml playbooks/erigon.yml --limit node_archive
```

## Usage

### Setup (Per Chain)

```bash
cd terraform/stacks/aws/ethereum/mainnet

# Configure HCP Terraform backend
cp cloud.tf.example cloud.tf

# Configure base variables
cp terraform.tfvars.example terraform.tfvars

# Configure node definitions
cp nodes.tfvars.example nodes.tfvars

# Initialize
terraform init
```

### Deploy Nodes

```bash
# Preview changes (recommended before apply)
terraform plan -var-file=nodes.tfvars

# Deploy all nodes defined in nodes.tfvars
# (also auto-generates ansible/inventory/ config file)
terraform apply -var-file=nodes.tfvars

# To add/remove nodes: edit nodes.tfvars, then re-apply
```

### Sepolia Testnet

Sepolia stacks are already provided for both platforms:

```bash
# AWS Sepolia
cd terraform/stacks/aws/ethereum/sepolia
cp cloud.tf.example cloud.tf
cp nodes.tfvars.example nodes.tfvars
terraform init && terraform apply -var-file=nodes.tfvars
# -> generates ansible/inventory/ethereum_sepolia_aws_terraform_state.yml

# Latitude Sepolia
cd terraform/stacks/latitude/ethereum/sepolia
cp cloud.tf.example cloud.tf
cp nodes.tfvars.example nodes.tfvars
terraform init && terraform apply -var-file=nodes.tfvars
# -> generates ansible/inventory/ethereum_sepolia_latitude_terraform_state.yml
```

Each network has isolated Terraform state - deploying Sepolia won't affect Mainnet.

### Adding a New Network

```bash
# Copy from existing network (e.g., adding holesky)
cp -r terraform/stacks/aws/ethereum/mainnet terraform/stacks/aws/ethereum/holesky

# Update variables
cd terraform/stacks/aws/ethereum/holesky
# Edit terraform.tfvars: set network = "holesky"
# Edit cloud.tf: create new workspace for holesky state
```

### Adding a New Chain

```bash
# Copy Ethereum template for a new chain
cp -r terraform/stacks/aws/ethereum terraform/stacks/aws/arbitrum

# Update variables for Arbitrum
cd terraform/stacks/aws/arbitrum/mainnet
# Edit terraform.tfvars, update project_name, chain, etc.
# terraform apply will auto-generate ansible/inventory/arbitrum_mainnet_terraform_state.yml
```

### Deploying Specific Nodes

Use `-target` to provision specific nodes without affecting others:

```bash
# Deploy only the full node
terraform apply -var-file=nodes.tfvars -target='module.compute["full"]'

# Deploy only the archive node
terraform apply -var-file=nodes.tfvars -target='module.compute["archive"]'

# Deploy multiple specific nodes
terraform apply -var-file=nodes.tfvars \
  -target='module.compute["full"]' \
  -target='module.compute["archive"]'

# Plan for specific node
terraform plan -var-file=nodes.tfvars -target='module.compute["full"]'
```

After Terraform provisions the infrastructure, use Ansible to configure and deploy services.

> **HAProxy (TLS + API key):** If deploying with HAProxy, create the Ansible vault files **before** running playbooks. See [Ansible Vault Setup](ansible.md#ansible-vault-setup). Without vault files, HAProxy deploys without API key protection.

Match the playbook to the `role` in your `nodes.tfvars`:

| `role` in nodes.tfvars | Playbook | Clients |
|------------------------|----------|---------|
| `ethereum` | `playbooks/ethereum.yml` | Docker: Geth+Prysm, Reth+Lighthouse |
| `erigon` | `playbooks/erigon.yml` | Binary: Erigon+Caplin |

> **Working directory:** Ansible commands must be run from the `ansible/` directory (the inventory plugin resolves Terraform state paths relative to this directory).

```bash
cd ansible
export TF_TOKEN_app_terraform_io="your-api-token"
export ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/your-key.pem
```

**Single role** (all nodes use the same playbook):

```bash
# All Docker nodes - AWS Mainnet
ansible-playbook -i inventory/ethereum_mainnet_aws_terraform_state.yml playbooks/ethereum.yml

# All Erigon nodes - AWS Mainnet
ansible-playbook -i inventory/ethereum_mainnet_aws_terraform_state.yml playbooks/erigon.yml
```

**Mixed roles** (e.g., Ethereum full node + Erigon archive node in the same inventory):

```bash
INV=inventory/ethereum_mainnet_aws_terraform_state.yml

# Run each playbook separately with --limit
ansible-playbook -i $INV playbooks/ethereum.yml --limit node_full
ansible-playbook -i $INV playbooks/erigon.yml --limit node_archive
```

**Specific node only:**

```bash
# Docker full node only
ansible-playbook -i inventory/ethereum_mainnet_aws_terraform_state.yml playbooks/ethereum.yml --limit node_full

# Erigon archive node only (AWS)
ansible-playbook -i inventory/ethereum_mainnet_aws_terraform_state.yml playbooks/erigon.yml --limit node_archive

# Erigon full node only (Latitude BM)
ansible-playbook -i inventory/ethereum_mainnet_latitude_terraform_state.yml playbooks/erigon.yml --limit node_full
```

**Latitude BM** (RAID-0 first, then node playbook):

```bash
INV=inventory/ethereum_mainnet_latitude_terraform_state.yml

ansible-playbook -i $INV playbooks/raid.yml
ansible-playbook -i $INV playbooks/erigon.yml
```

**Sepolia:**

```bash
# AWS Sepolia
ansible-playbook -i inventory/ethereum_sepolia_aws_terraform_state.yml playbooks/erigon.yml

# Latitude BM Sepolia
ansible-playbook -i inventory/ethereum_sepolia_latitude_terraform_state.yml playbooks/erigon.yml
```

For the full list of deployment scenarios, see the [Ansible Deployment Scenarios](ansible.md#deployment-scenarios).

### Other Commands

```bash
# Preview changes
terraform plan -var-file=nodes.tfvars

# View outputs
terraform output

# Destroy all nodes
terraform destroy -var-file=nodes.tfvars

# To remove a specific node: remove it from nodes.tfvars, then apply
```

## Outputs

| Output | Description |
|--------|-------------|
| `vpc_id` | VPC ID |
| `instance_info` | EC2 instance details |
| `instance_ids` | EC2 instance IDs |
| `ansible_inventory_file` | Path to auto-generated Ansible inventory file |
| `dns_records` | Route 53 A records (FQDN + IP) for nodes with domains |

## DNS (Route 53 A Records)

Terraform can automatically create Route 53 A records pointing domain names to node IPs. This is required for HAProxy TLS termination - Certbot issues certs for the domain, and clients resolve the domain to reach the node.

### Setup

1. Set `route53_zone_id` in `terraform.tfvars`:
   ```hcl
   route53_zone_id = "Z0123456789ABCDEFGHIJ"
   ```
   Find your zone ID:
   ```bash
   aws route53 list-hosted-zones --query 'HostedZones[*].[Name,Id]' --output table
   ```
   If any node has `domain` set and `route53_zone_id` is empty, Terraform fails with a validation check.

2. Add `domain` to nodes in `nodes.tfvars`:
   ```hcl
   nodes = {
     full = {
       ...
       associate_eip = true
       domain        = "full.rpc.eth.example.com"
     }
   }
   ```

3. Apply:
   ```bash
   terraform apply -var-file=nodes.tfvars
   ```

### How It Works

- A records are only created for nodes with a non-empty `domain` field
- Points to `effective_public_ip` (EIP if attached, else dynamic public IP)
- TTL is 300 seconds (5 minutes)
- The domain is passed to Ansible as `haproxy_domain` host variable, overriding the global default from `group_vars/all/main.yml`
- Nodes without `domain` set do not get a Route 53 record

### Recommendations

- Use `associate_eip = true` for nodes with domains (EIPs persist across instance stop/start)
- Without an EIP, the A record updates automatically on `terraform apply` when the instance gets a new IP, but there is a brief DNS stale window (limited by the 300s TTL)

## Security Considerations

1. **VPN access**: SSH restricted to VPN/office IP ranges only
2. **IMDSv2**: Instance metadata requires tokens
3. **Security groups**: Per-client P2P SGs (each node gets only ports for its clients), SSH from VPN, HAProxy 80/443 from internet
4. **SSH keys**: Create key pair in AWS Console, never commit private keys
5. **IAM instance profile**: Scoped to Route 53 only (Certbot DNS-01 for HAProxy TLS certificates), narrowed to the configured hosted zone when `route53_zone_id` is set

### SSH Key Management

1. Create key pair in AWS EC2 Console or CLI:
   ```bash
   aws ec2 create-key-pair --key-name blockchain-prod --query 'KeyMaterial' --output text > ~/.ssh/blockchain-prod.pem
   chmod 400 ~/.ssh/blockchain-prod.pem
   ```

2. Reference key name in `terraform.tfvars`:
   ```hcl
   key_name = "blockchain-prod"
   ```

3. Use SSH agent or set Ansible key via environment:
   ```bash
   export ANSIBLE_PRIVATE_KEY_FILE="~/.ssh/blockchain-prod.pem"
   ```
