#!/usr/bin/env bash

set -euo pipefail

make install
apm install --frozen
