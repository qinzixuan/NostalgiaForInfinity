#!/usr/bin/env bash
# 统一的 FreqAI 数据下载、训练、预测入口，便于在不同模式间切换。
# 用法：MODE=download|train|predict|both ./tools/freqai/pipeline.sh
set -euo pipefail

MODE=${MODE:-both}
CONFIG=${CONFIG:-configs/freqai-config.example.json}
STRATEGY=${STRATEGY:-NostalgiaForInfinityX7Freqai}
MODELS_PATH=${MODELS_PATH:-user_data/freqaimodels}
DATA_DIR=${DATA_DIR:-user_data/data}
PAIRLIST=${PAIRLIST:-"BTC/USDT ETH/USDT"}
TIMEFRAMES=${TIMEFRAMES:-"5m 15m 1h 4h"}
TIMERANGE=${TIMERANGE:--90d}

patch_config() {
  local mode=$1
  local tmp=$(mktemp)
  jq --arg mode "$mode" '.freqai.process_to_use = $mode' "$CONFIG" > "$tmp"
  echo "$tmp"
}

run_download() {
  freqtrade download-data \
    --config "$CONFIG" \
    --timeframes $TIMEFRAMES \
    --timerange "$TIMERANGE" \
    --dataformat-ohlcv feather \
    --datadir "$DATA_DIR" \
    --pairs $PAIRLIST
}

run_trade_with_mode() {
  local mode=$1
  local patched
  patched=$(patch_config "$mode")
  freqtrade trade \
    --config "$patched" \
    --strategy "$STRATEGY" \
    --freqaimodels-path "$MODELS_PATH" \
    --datadir "$DATA_DIR" \
    --disable-trading
  rm -f "$patched"
}

case "$MODE" in
  download)
    run_download
    ;;
  train)
    run_download
    run_trade_with_mode "train"
    ;;
  predict)
    run_trade_with_mode "predict"
    ;;
  both)
    run_download
    run_trade_with_mode "both"
    ;;
  *)
    echo "未知 MODE: $MODE" >&2
    exit 1
    ;;
 esac
