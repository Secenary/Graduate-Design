#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

KG_PATH_ARG=()
if [[ -n "${KG_PATH:-}" ]]; then
  KG_PATH_ARG=(--kg-path "$KG_PATH")
fi

python -m scripts.prepare_term_matching_data \
  "${KG_PATH_ARG[@]}" \
  --state-path "${STATE_PATH:-results/kg_enhancement_state.json}" \
  --train-output "${TRAIN_OUTPUT:-training_data/sft_term_matching_train.jsonl}" \
  --val-output "${VAL_OUTPUT:-training_data/sft_term_matching_val.jsonl}" \
  --stats-output "${STATS_OUTPUT:-training_data/term_matching_stats.json}" \
  --max-candidates "${MAX_CANDIDATES:-6}" \
  --val-ratio "${VAL_RATIO:-0.1}" \
  --auto-negative-limit "${AUTO_NEGATIVE_LIMIT:-24}"

llamafactory-cli train "${LLAMAFACTORY_CONFIG:-training_configs/llamafactory_qwen25_14b_term_matching.yaml}"
