#!/usr/bin/env bash
set -euo pipefail
run_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
run_python="${RUN35K_PYTHON:-python}"
"$run_python" -u "$run_dir/collect.py"
"$run_python" -u "$run_dir/train.py" "$@"
