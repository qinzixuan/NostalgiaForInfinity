# 将 NostalgiaForInfinity 系列接入 FreqAI 的操作指南

本指南描述如何在现有的 NostalgiaForInfinity 策略（如 `NostalgiaForInfinityX7.py`）基础上启用 FreqAI。内容聚焦于配置与迁移步骤，而不改变策略的核心因子逻辑。

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
3. 根据自身环境调整 `user_data/freqai-config.json` 中的 `datadir`、`timeframe`、API 密钥与交易对列表。

## 2. 配置 FreqAI 基本参数
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

## 3. 为 NostalgiaForInfinity 创建 FreqAI 版本的策略文件
建议基于官方示例（`freqtrade/templates/freqai_example_strategy.py`）新建策略，如 `user_data/strategies/NostalgiaForInfinityX7Freqai.py`，并迁移现有特征：

1. 继承示例中的 FreqAI 基类，并保留 `process_only_new_candles=True`、`startup_candle_count` 等与原策略匹配的设置。
2. 在 `freqai_info` 中配置要输出给模型的特征，优先使用原策略已经计算好的因子（如多时框 RSI、AROON、布林带、EMA 差值等），避免重复实现。
3. 将现有 `populate_indicators` 中的指标计算逻辑迁移/复用到新策略，以便同时服务传统规则与 FreqAI 特征生成。
4. 在 `populate_entry_trend` / `populate_exit_trend` 中，引入模型预测结果（如预测的未来收益率）作为过滤条件，保留关键的保护逻辑（黑名单、全局保护）以降低回测/实盘偏差。

> 提示：保持与原版相同的时间框架（5m 主周期 + 15m/1h/4h/1d 信息源），否则原有保护与加仓节奏会失效。

## 4. 训练与运行流程
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

## 5. 与现有加仓/保护逻辑的协作建议
- **平滑迁移**：初期可在 `populate_entry_trend` 中要求“规则信号 + 模型看多”双重条件，逐步验证模型的增益；稳定后再放宽为“模型看多 + 保护通过”。
- **风控优先**：保留原策略的全局保护、黑名单与仓位上限设置，并在 `config` 里增加较紧的 `minimal_roi` / 跟踪止损，以应对模型误判。
- **数据一致性**：确保 `include_timeframes` 与策略实际计算的 informatives 一致，否则训练数据与实盘特征会出现漂移。

通过以上步骤，你可以在不破坏 NostalgiaForInfinity 现有交易逻辑的前提下，引入 FreqAI 的建模能力，并在回测和实盘中循序评估其效果。
