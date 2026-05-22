#!/bin/bash
# Deploy script for snmp-switch-manager integration
# Deploys the current workspace code to the Home Assistant instance at 10.0.12.246

set -e

HA_HOST="10.0.12.246"
HA_USER="root"
TARGET_DIR="/homeassistant/custom_components/snmp_switch_manager/"

echo "============================================="
echo "🚀 Deploying snmp-switch-manager to HA host..."
echo "Target: ${HA_USER}@${HA_HOST}:${TARGET_DIR}"
echo "============================================="

# Sync local custom_components/snmp_switch_manager/ to remote
# --delete ensures we remove files that are no longer part of the refactored branch
# --exclude avoids transferring compiled files or local caches
rsync -avzh --delete \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='.ruff_cache/' \
  custom_components/snmp_switch_manager/ \
  "${HA_USER}@${HA_HOST}:${TARGET_DIR}"

echo "============================================="
echo "✅ Deployment completed successfully!"
echo "⚠️  Remember to restart Home Assistant to apply changes."
echo "============================================="
