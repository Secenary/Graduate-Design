#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python -m venv .venv-llamafactory
source .venv-llamafactory/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install "llamafactory[torch,metrics]"

python - <<'PY'
import torch
print('cuda_available =', torch.cuda.is_available())
if torch.cuda.is_available():
    print('device =', torch.cuda.get_device_name(0))
PY
