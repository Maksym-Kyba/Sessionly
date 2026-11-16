#!/bin/bash
# First-boot setup for the Sessionly server: swap, Docker and the application directory.
set -euo pipefail

# Swap gives the 2 GiB instance headroom while Docker builds the frontend image.
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2 git
systemctl enable --now docker
usermod -aG docker ubuntu

mkdir -p /opt/sessionly
chown ubuntu:ubuntu /opt/sessionly
