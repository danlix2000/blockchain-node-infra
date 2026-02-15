output "vpc_id" {
  value = aws_vpc.main.id
}

output "subnet_ids" {
  value = [for s in aws_subnet.main : s.id]
}

output "ssh_sg_id" {
  value = aws_security_group.ssh.id
}

output "p2p_sg_ids" {
  description = "Per-client P2P security group IDs"
  value = {
    execution  = aws_security_group.p2p_execution.id
    erigon     = aws_security_group.p2p_erigon.id
    lighthouse = aws_security_group.p2p_lighthouse.id
    prysm      = aws_security_group.p2p_prysm.id
  }
}

output "haproxy_sg_id" {
  value = aws_security_group.haproxy.id
}
