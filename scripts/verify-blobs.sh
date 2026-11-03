#!/bin/sh
# SPDX-FileCopyrightText: 2026 The open27xx Authors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Check the files in blobs/ against scripts/blobs.sha256.

set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
list=$root/scripts/blobs.sha256
cd "$root/blobs"

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum --check --quiet "$list"
else
  shasum -a 256 --check --quiet "$list"
fi

echo "blobs: $(wc -l < "$list" | tr -d ' ') files match scripts/blobs.sha256"
