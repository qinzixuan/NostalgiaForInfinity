# 将 NostalgiaForInfinity 系列接入 FreqAI 的操作指南

本指南描述如何在现有的 NostalgiaForInfinity 策略（如 `NostalgiaForInfinityX7.py`）基础上启用 FreqAI。内容聚焦于配置与迁移步骤，而不改变策略的核心因子逻辑。

## 0. 推进路线图（分步执行，避免破坏现有规则）
1. **环境拆分与容器入口准备（已完成）**：为默认版与 FreqAI 版提供独立的 docker compose 文件、默认配置模板与运行命令，确保随时可切换并回退。
2. **策略与特征迁移（已完成）**：基于 `NostalgiaForInfinityX7` 派生 FreqAI 版策略，复用已有指标与保护逻辑，将其暴露为 FreqAI 特征，同时保持原版可继续运行。
3. **训练管线与模型发布（当前步骤）**：补充训练/验证脚本、定时任务与模型版本目录（`user_data/freqaimodels`），定义回退策略与观测指标，确保上线前可快速滚回上一模型。
4. **实盘切换与监控**：在 FreqAI 容器中开启滚动训练/预测，增加 API 监控与告警，完成稳定性验证后再逐步提高持仓与交易对范围。

当前进度：已完成环境拆分、策略迁移，并新增训练/预测管线脚本，可直接运行 FreqAI 训练/纸交易，原策略逻辑保持不变。

## 1. 环境准备
1. 安装带 FreqAI 依赖的 Freqtrade 版本：
   ```bash
   pip install "freqtrade[ai]"
   ```
2. 复制官方的 FreqAI 配置模板（通常位于 `freqtrade/templates/freqai_config.json`），作为新的运行配置，例如：
   ```bash
   cp $(python - <<'PY'
import importlib.util, pathlib
spec = importlib.util.find_spec('freqtrade')
print(pathlib.Path(spec.origin).resolve().parent / 'templates' / 'freqai_config.json')
PY) user_data/freqai-config.json
   ```
3. 根据自身环境调整 `user_data/freqai-config.json` 中的 `datadir`、`timeframe`、API 密钥与交易对列表。若希望直接在本仓库内管理示例配置，可以 `configs/freqai-config.example.json` 为模板拷贝、修改并通过环境变量 `FREQAI_CONFIG` 指向它。

## 2. Docker 部署与多版本切换
- **默认版（非 FreqAI）**：继续使用根目录的 `docker-compose.yml`，例如：
  ```bash
  docker compose -f docker-compose.yml up -d freqtrade
  ```
- **FreqAI 版（当前新增）**：使用新文件 `docker-compose.freqai.yml`，默认挂载 `configs/freqai-config.example.json`，并将模型存入 `user_data/freqaimodels`。
  ```bash
  # 首次创建模型目录
  mkdir -p user_data/freqaimodels

  # 以示例配置启动 FreqAI 版容器
  docker compose -f docker-compose.freqai.yml up -d freqtrade-freqai
  ```
  若需要指定自定义配置文件，可在 `.env` 中设置 `FREQAI_CONFIG=configs/my-freqai-config.json`（或启动时以环境变量传入），其余容器参数与默认版保持一致，便于快速回退。

## 3. NostalgiaForInfinityX7Freqai 策略骨架
- **继承与兼容性**：`NostalgiaForInfinityX7Freqai` 直接继承原版 `NostalgiaForInfinityX7`，沿用全部指标、保护与加仓规则；仅在进场前加入模型预测的方向过滤，并附加 `|ai_long` / `|ai_short` 标记以便区分。
- **特征与标签**：
- 自动扩展的特征：RSI/MFI/ADX/ROC、布林宽度、价格相对布林下轨、成交量 z-score，按 `indicator_periods` 与 `include_timeframes`、`include_corr_pairlist` 自动展开。
  - 主周期特征：价格涨幅、VWAP 比、原始收盘价/成交量，以及小时、星期等时间特征。
  - 训练标签：`&-future_roi`（未来 12 根的收益率），用于正负方向判定。
- **启用方式**：
  1. 确认配置文件的 `strategy` 指向 `NostalgiaForInfinityX7Freqai`（示例文件已默认设置）。
  2. 在 FreqAI 容器内运行时保持 `--freqai` 开关，或在本地执行：
     ```bash
     freqtrade trade \
       --config configs/freqai-config.example.json \
       --strategy NostalgiaForInfinityX7Freqai \
       --freqaimodels-path user_data/freqaimodels
     ```
  3. 若要仅验证策略而暂不使用模型，可在配置中将 `freqai.enabled` 设为 `false`，策略将退化为原版规则。

## 4. 配置 FreqAI 基本参数
`user_data/freqai-config.json` 的 `freqai` 段落是核心。以下字段通常需要确认：

- `enabled`: 设为 `true` 以启用 FreqAI。
- `process_to_use`: 选择 `train`、`predict` 或 `both`（实盘建议 `both` 以便滚动训练+预测）。
- `auto_load_models` / `auto_save_models`: 设为 `true` 以在启动/训练后自动加载与保存模型。
- `feature_parameters.include_timeframes`: 列出需要作为特征的时间框（保留策略主周期 5m，并可追加 15m/1h/4h 等）。
- `feature_parameters.include_corr_pairlist`: 如果想引入 BTC/ETH 等相关币对指标，按需列出；与原策略的多时框信息源一致即可。
- `label_parameters`: 指定训练标签，常见是短周期的未来收益率或分类标签（可参考官方模板 `roi_label` 方案）。
- `data_split_parameters`: 训练/验证划分，例如 `{"split_ratio": 0.8}`。
- `training_parameters` / `live_training_parameters`: 设定模型与滚动训练频率（如 XGBoost/LightGBM 的超参、每隔多少根 K 线再训练）。

保持其余资金、风控参数与当前策略 `config.json` 一致，以减少变量。

## 5. 为 NostalgiaForInfinity 创建 FreqAI 版本的策略文件
建议基于官方示例（`freqtrade/templates/freqai_example_strategy.py`）新建策略，如 `user_data/strategies/NostalgiaForInfinityX7Freqai.py`，并迁移现有特征：

1. 继承示例中的 FreqAI 基类，并保留 `process_only_new_candles=True`、`startup_candle_count` 等与原策略匹配的设置。
2. 在 `freqai_info` 中配置要输出给模型的特征，优先使用原策略已经计算好的因子（如多时框 RSI、AROON、布林带、EMA 差值等），避免重复实现。
3. 将现有 `populate_indicators` 中的指标计算逻辑迁移/复用到新策略，以便同时服务传统规则与 FreqAI 特征生成。
4. 在 `populate_entry_trend` / `populate_exit_trend` 中，引入模型预测结果（如预测的未来收益率）作为过滤条件，保留关键的保护逻辑（黑名单、全局保护）以降低回测/实盘偏差。

> 提示：保持与原版相同的时间框架（5m 主周期 + 15m/1h/4h/1d 信息源），否则原有保护与加仓节奏会失效。

### 3.1 快速训练/预测脚本
- 新增 `tools/freqai/pipeline.sh`，封装下载数据 + 训练/预测的常用流程，避免手工修改配置：
  ```bash
  # 仅下载 90 天的多周期数据
  MODE=download ./tools/freqai/pipeline.sh

  # 下载 + 训练（process_to_use=train），结果保存到 user_data/freqaimodels
  MODE=train ./tools/freqai/pipeline.sh

  # 使用已训练模型跑预测（不下单），用于验证特征与模型输出
  MODE=predict ./tools/freqai/pipeline.sh

  # 下载 + 训练 + 预测（process_to_use=both），常用于滚动训练
  MODE=both ./tools/freqai/pipeline.sh
  ```
- 通过环境变量可覆盖关键参数：`CONFIG`（配置路径）、`STRATEGY`、`PAIRLIST`、`TIMEFRAMES`、`TIMERANGE`、`DATA_DIR` 与 `MODELS_PATH`。脚本会在临时文件中注入 `freqai.process_to_use`，并使用 `--disable-trading` 确保仅生成模型/预测，不触发真实下单。
 通过环境变量可覆盖关键参数：`CONFIG`（配置路径）、`STRATEGY`、`PAIRLIST`、`TIMEFRAMES`、`TIMERANGE`、`DATA_DIR` 与 `MODELS_PATH`。脚本会在临时文件中注入 `freqai.process_to_use`，并使用 `--disable-trading` 确保仅生成模型/预测，不触发真实下单；依赖 `freqtrade` 与 `jq` 可执行程序。

## 6. 训练与运行流程
1. 首次训练：
   ```bash
   freqtrade trade \
     --config user_data/freqai-config.json \
     --strategy NostalgiaForInfinityX7Freqai \
     --freqaimodels-path user_data/freqaimodels \
     --datadir user_data/data
   ```
   当 `process_to_use` 包含 `train` 时会自动生成/更新模型。

2. 仅预测（使用已有模型）：
   ```bash
   freqtrade trade \
     --config user_data/freqai-config.json \
     --strategy NostalgiaForInfinityX7Freqai \
     --process-only-dataframe \
     --freqaimodels-path user_data/freqaimodels
   ```

3. 日常维护：定期检查 `user_data/freqaimodels` 下的模型版本，评估新旧模型收益差异；在市场结构变化明显时执行重新训练。

## 7. 与现有加仓/保护逻辑的协作建议
- **平滑迁移**：初期可在 `populate_entry_trend` 中要求“规则信号 + 模型看多”双重条件，逐步验证模型的增益；稳定后再放宽为“模型看多 + 保护通过”。
- **风控优先**：保留原策略的全局保护、黑名单与仓位上限设置，并在 `config` 里增加较紧的 `minimal_roi` / 跟踪止损，以应对模型误判。
- **数据一致性**：确保 `include_timeframes` 与策略实际计算的 informatives 一致，否则训练数据与实盘特征会出现漂移。

通过以上步骤，你可以在不破坏 NostalgiaForInfinity 现有交易逻辑的前提下，引入 FreqAI 的建模能力，并在回测和实盘中循序评估其效果。