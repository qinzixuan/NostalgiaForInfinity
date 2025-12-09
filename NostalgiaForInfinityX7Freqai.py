import logging
from typing import Any, Dict

import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.freqai.freqai_strategy import FreqaiStrategy
from NostalgiaForInfinityX7 import NostalgiaForInfinityX7

logger = logging.getLogger(__name__)


class NostalgiaForInfinityX7Freqai(FreqaiStrategy, NostalgiaForInfinityX7):
    """NostalgiaForInfinity 的 FreqAI 兼容版。

    核心交易规则沿用 `NostalgiaForInfinityX7`，在进场前增加基于模型的过滤，
    并通过 FreqAI 的特征工程接口暴露基础特征与训练标签。
    """

    freqai_info: Dict[str, Any] = {
        "feature_parameters": {
            "include_timeframes": ["5m", "15m", "1h", "4h"],
            "include_corr_pairlist": ["BTC/USDT", "ETH/USDT"],
            "indicator_periods": [14, 28, 56],
        },
        "label_parameters": {
            "label_type": "roi_label",
            "label_period_candles": 12,
            "roi_multiplier": 1.0,
        },
        "data_split_parameters": {"split_ratio": 0.8},
        "training_parameters": {
            "model": "LightGBMRegressor",
            "n_estimators": 400,
            "learning_rate": 0.05,
            "max_depth": -1,
        },
        "live_training_parameters": {
            "train_period_days": 30,
            "retrain_interval_minutes": 120,
            "warmup_candles": 900,
        },
        "prediction_parameters": {"prediction_length": 1},
    }

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs: Any
    ) -> DataFrame:
        """在自动扩展的周期/时间框上生成基础技术指标特征。"""

        dataframe["%-rsi-period"] = ta.RSI(dataframe, timeperiod=period)
        dataframe["%-mfi-period"] = ta.MFI(dataframe, timeperiod=period)
        dataframe["%-adx-period"] = ta.ADX(dataframe, timeperiod=period)
        dataframe["%-roc-period"] = ta.ROC(dataframe, timeperiod=period)

        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=period, stds=2.2
        )
        dataframe["%-bb_width-period"] = (
            (bollinger["upper"] - bollinger["lower"]) / bollinger["mid"]
        )
        dataframe["%-close_to_bblow-period"] = dataframe["close"] / bollinger["lower"]

        dataframe["%-volume_zscore-period"] = (
            (dataframe["volume"] - dataframe["volume"].rolling(period).mean())
            / dataframe["volume"].rolling(period).std()
        )

        return dataframe

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs: Any
    ) -> DataFrame:
        """在基础时间框上添加不依赖周期扩展的特征。"""

        dataframe["%-pct_change"] = dataframe["close"].pct_change()
        dataframe["%-raw_volume"] = dataframe["volume"]
        dataframe["%-raw_close"] = dataframe["close"]
        dataframe["%-vwap_ratio"] = dataframe["close"] / qtpylib.typical_price(dataframe)

        return dataframe

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs: Any
    ) -> DataFrame:
        """在主周期上添加不会被自动扩展的特征。"""

        dataframe["%-hour_of_day"] = dataframe["date"].dt.hour
        dataframe["%-day_of_week"] = dataframe["date"].dt.dayofweek
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs: Any) -> DataFrame:
        """定义未来收益率标签，供模型训练与实时预测。"""

        horizon = self.freqai_info["label_parameters"]["label_period_candles"]
        dataframe["&-future_roi"] = (
            dataframe["close"].shift(-horizon) / dataframe["close"] - 1
        )
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 先调用原策略的指标计算，保持现有规则完整
        dataframe = NostalgiaForInfinityX7.populate_indicators(self, dataframe, metadata)

        # 调用 FreqAI 管道，生成特征、目标与预测列（在未安装 FreqAI 时安全跳过）
        if hasattr(self, "freqai"):
            dataframe = self.freqai.start(dataframe, metadata, self)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = NostalgiaForInfinityX7.populate_entry_trend(self, dataframe, metadata)

        if {"do_predict", "&-future_roi"}.issubset(dataframe.columns):
            long_mask = (dataframe["enter_long"] == 1) & (dataframe["do_predict"] == 1)
            short_mask = (dataframe["enter_short"] == 1) & (dataframe["do_predict"] == 1)

            dataframe.loc[
                long_mask & (dataframe["&-future_roi"] <= 0), ["enter_long", "enter_tag"]
            ] = (0, None)
            dataframe.loc[
                short_mask & (dataframe["&-future_roi"] >= 0), ["enter_short", "enter_tag"]
            ] = (0, None)

            dataframe.loc[long_mask & (dataframe["&-future_roi"] > 0), "enter_tag"] = (
                dataframe.loc[long_mask & (dataframe["&-future_roi"] > 0), "enter_tag"].fillna("")
                + "|ai_long"
            )
            dataframe.loc[
                short_mask & (dataframe["&-future_roi"] < 0), "enter_tag"
            ] = (
                dataframe.loc[
                    short_mask & (dataframe["&-future_roi"] < 0), "enter_tag"
                ].fillna("")
                + "|ai_short"
            )

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 沿用原有的退出逻辑（默认无主动退出），FreqAI 不额外干预
        return super().populate_exit_trend(dataframe, metadata)
