#!/usr/bin/env bash
#
# config-upgrade.sh - Upgrade config.yaml to match config.example.yaml

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE="$REPO_ROOT/config.example.yaml"

# ── Find uv ────────────────────────────────────────────────────────────────────
find_uv() {
    if command -v uv >/dev/null 2>&1; then
        echo "uv"
        return 0
    fi
    if [ -f "/mnt/c/Python314/Scripts/uv.exe" ]; then
        echo "/mnt/c/Python314/Scripts/uv.exe"
        return 0
    fi
    for pyver in 312 313; do
        if [ -f "/mnt/c/Python${pyver}/Scripts/uv.exe" ]; then
            echo "/mnt/c/Python${pyver}/Scripts/uv.exe"
            return 0
        fi
    done
    return 1
}

UV_CMD="$(find_uv)"
if [ -z "$UV_CMD" ]; then
    echo "Error: uv not found. Please install uv."
    exit 1
fi

# Resolve config.yaml location
if [ -n "$DEER_FLOW_CONFIG_PATH" ] && [ -f "$DEER_FLOW_CONFIG_PATH" ]; then
    CONFIG="$DEER_FLOW_CONFIG_PATH"
elif [ -f "$REPO_ROOT/backend/config.yaml" ]; then
    CONFIG="$REPO_ROOT/backend/config.yaml"
elif [ -f "$REPO_ROOT/config.yaml" ]; then
    CONFIG="$REPO_ROOT/config.yaml"
else
    CONFIG=""
fi

if [ ! -f "$EXAMPLE" ]; then
    echo "Error: config.example.yaml not found"
    exit 1
fi

if [ -z "$CONFIG" ]; then
    echo "No config.yaml found - creating from example..."
    cp "$EXAMPLE" "$REPO_ROOT/config.yaml"
    echo "Done. Please review and set your API keys."
    exit 0
fi

# Convert Unix-style paths to Windows paths for Python
# /mnt/d/... -> D:\...  or /mnt/c/... -> C:\...
unix_to_windows_path() {
    local path="$1"
    case "$path" in
        /mnt/d/*) echo "D:${path#/mnt/d}" ;;
        /mnt/c/*) echo "C:${path#/mnt/c}" ;;
        *) echo "$path" ;;
    esac
}

CONFIG_WIN=$(unix_to_windows_path "$CONFIG")
EXAMPLE_WIN=$(unix_to_windows_path "$EXAMPLE")

cd "$REPO_ROOT/backend"

"$UV_CMD" run python -c "
import os
import sys
import shutil
import copy
from pathlib import Path

config_path = Path(r'${CONFIG_WIN//\\/\\\\}')
example_path = Path(r'${EXAMPLE_WIN//\\/\\\\}')

import yaml

with open(config_path, encoding='utf-8') as f:
    raw_text = f.read()
    user = yaml.safe_load(raw_text) or {}

with open(example_path, encoding='utf-8') as f:
    example = yaml.safe_load(f) or {}

user_version = user.get('config_version', 0)
example_version = example.get('config_version', 0)

if user_version >= example_version:
    print(f'OK config.yaml is already up to date (version {user_version}).')
    sys.exit(0)

print(f'Upgrading config.yaml: version {user_version} -> {example_version}')
print()

# Migrations
MIGRATIONS = {
    1: {
        'replacements': [
            ('src.community.', 'deerflow.community.'),
            ('src.sandbox.', 'deerflow.sandbox.'),
            ('src.models.', 'deerflow.models.'),
            ('src.tools.', 'deerflow.tools.'),
        ],
    },
}

migrated = []
for version in range(user_version + 1, example_version + 1):
    migration = MIGRATIONS.get(version)
    if not migration:
        continue
    for old, new in migration.get('replacements', []):
        if old in raw_text:
            raw_text = raw_text.replace(old, new)
            migrated.append(f'{old} -> {new}')

user = yaml.safe_load(raw_text) or {}

if migrated:
    print(f'Applied {len(migrated)} migration(s):')
    for m in migrated:
        print(f'  ~ {m}')
    print()

# Merge missing fields
added = []

def merge(target, source, path=''):
    for key, value in source.items():
        key_path = f'{path}.{key}' if path else key
        if key not in target:
            target[key] = copy.deepcopy(value)
            added.append(key_path)
        elif isinstance(value, dict) and isinstance(target[key], dict):
            merge(target[key], value, key_path)

merge(user, example)
user['config_version'] = example_version

# Write
backup = config_path.with_suffix('.yaml.bak')
shutil.copy2(config_path, backup)
print(f'Backed up to {backup.name}')

with open(config_path, 'w', encoding='utf-8') as f:
    yaml.dump(user, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

if added:
    print(f'Added {len(added)} new field(s):')
    for a in added:
        print(f'  + {a}')

if not migrated and not added:
    print('No changes needed (version bumped only).')

print()
print(f'OK config.yaml upgraded to version {example_version}.')
print('  Please review the changes and set any new required values.')
"
