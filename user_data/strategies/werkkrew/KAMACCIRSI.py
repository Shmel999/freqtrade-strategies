# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement

# --- Do not remove these libs ---
from functools import reduce
import numpy as np  # noqa
import pandas as pd  # noqa
from pandas import DataFrame

from freqtrade.strategy import IStrategy

# --------------------------------
# Add your lib to import here
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class KAMACCIRSI(IStrategy):
    """
    author@: werkkrew
    github@: https://github.com/werkkrew/freqtrade-strategies

    Strategy using 3 indicators with fully customizable parameters and full hyperopt support
    including indicator periods as well as cross points.

    There is nothing groundbreaking about this strategy, how it works, or what it does. 
    It was mostly an experiment for me to learn Freqtrade strategies and hyperopt development.

    Default hyperopt defined parameters below were done on 60 days of data from Kraken against 20 BTC pairs
    using the SharpeHyperOptLoss loss function.

    Suggestions and improvements are welcome!

    Supports selling via strategy, as well as ROI and Stoploss/Trailing Stoploss

    Indicators Used:
    KAMA "Kaufman Adaptive Moving Average" (Short Duration)
    KAMA (Long Duration)
    CCI "Commodity Channel Index"
    RSI "Relative Strength Index"

    Buy Strategy:
        kama-cross OR kama-slope 
            kama-short > kama-long
            kama-long-slope > 1
        cci-enabled? 
            cci > X 
        rsi-enabled?
            rsi > Y 

    Sell Strategy:
        kama-cross OR kama-slope 
            kama-short < kama-long
            kama-long-slope < 1
        cci-enabled?
            cci < A
        rsi-enabled?
            rsi < B

    Ideas and Todo:
        - Add informative pairs to help decision (e.g. BTC/USD to inform other */BTC pairs)
    """
    # Strategy interface version - allow new iterations of the strategy interface.
    # Check the documentation or the Sample strategy to get the latest version.
    INTERFACE_VERSION = 2

    """
    HYPEROPT SETTINGS
    The following is set by Hyperopt, or can be set by hand if you wish:

    - minimal_roi table
    - stoploss
    - trailing stoploss
    - for buy/sell separate
        - kama-trigger = cross, slope
        - kama-short timeperiod
        - kama-long timeperiod
        - cci period
        - cci upper / lower threshold
        - rsi period
        - rsi upper / lower threshold

    PASTE OUTPUT FROM HYPEROPT HERE
    """

    # Buy hyperspace params (optimized alone (2/11/21)):
    # 927/1000:    194 trades. 123/68/3 Wins/Draws/Losses. Avg profit   1.18%. Median profit   0.26%. Total profit  0.00228732 BTC ( 228.36Σ%). Avg duration 863.4 min. Objective: -37.11041
    buy_params = {
        'cci-enabled': False,
        'cci-limit': 137,
        'cci-period': 34,
        'kama-long-period': 42,
        'kama-short-period': 13,
        'kama-trigger': 'cross',
        'rsi-enabled': True,
        'rsi-limit': 70,
        'rsi-period': 23
    }

    # Sell hyperspace params: (optimized alone (2/11/21))
    # 198/1000:    196 trades. 118/76/2 Wins/Draws/Losses. Avg profit   1.21%. Median profit   0.17%. Total profit  0.00238257 BTC ( 237.87Σ%). Avg duration 822.2 min. Objective: -43.77210
    sell_params = {
        'sell-cci-enabled': False,
        'sell-cci-limit': -165,
        'sell-cci-period': 50,
        'sell-kama-long-period': 70,
        'sell-kama-short-period': 7,
        'sell-kama-trigger': 'slope',
        'sell-rsi-enabled': True,
        'sell-rsi-limit': 79,
        'sell-rsi-period': 27
    }

    # ROI table: (optimized alone 2/11/21)
    # 2821/5000:    196 trades. 118/76/2 Wins/Draws/Losses. Avg profit   1.21%. Median profit   0.17%. Total profit  0.00237930 BTC ( 237.55Σ%). Avg duration 822.0 min. Objective: -43.68932
    minimal_roi = {
        "0": 0.10641,
        "16": 0.04562,
        "75": 0.03079,
        "195": 0
    }

    # Stoploss: (optimized alone 2/11/21)
    # 6/1000:     176 trades. 115/57/4 Wins/Draws/Losses. Avg profit   1.08%. Median profit   0.30%. Total profit  0.00191173 BTC ( 190.87Σ%). Avg duration 954.9 min. Objective: -22.30542
    stoploss = -0.31878

    # Trailing stop: (optimized alone 2/11/21)
    # 19/1000:    176 trades. 115/57/4 Wins/Draws/Losses. Avg profit   1.04%. Median profit   0.30%. Total profit  0.00182933 BTC ( 182.64Σ%). Avg duration 954.8 min. Objective: -22.34594
    trailing_stop = True
    trailing_stop_positive = 0.06276
    trailing_stop_positive_offset = 0.10079
    trailing_only_offset_is_reached = False

    """
    END HYPEROPT
    """

    timeframe = '5m'

    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = False

    # These values can be overridden in the "ask_strategy" section in the config.
    use_sell_signal = True
    sell_profit_only = True
    ignore_roi_if_buy_signal = True

    # Number of candles the strategy requires before producing valid signals
    # Set this to the highest period value in the indicator_params dict or highest of the ranges in the hyperopt settings (default: 72)
    startup_candle_count: int = 72

    # Optional order type mapping.
    order_types = {
        'buy': 'limit',
        'sell': 'limit',
        'emergencysell': 'market',
        'stoploss': 'market',
        'stoploss_on_exchange': True,
        'stoploss_on_exchange_interval': 60,
        'stoploss_on_exchange_limit_ratio': 0.99
    }

    # Optional order time in force.
    order_time_in_force = {
        'buy': 'gtc',
        'sell': 'gtc'
    }
    
    """
    Not currently being used for anything, thinking about implementing this later.
    """
    def informative_pairs(self):
        # https://www.freqtrade.io/en/latest/strategy-customization/#additional-data-informative_pairs
        informative_pairs = [(f"{self.config['stake_currency']}/USD", self.timeframe)]
        return informative_pairs

    """
    Populate all of the indicators we need (note: indicators are separate for buy/sell)
    """
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # # Commodity Channel Index: values [Oversold:-100, Overbought:100]
        dataframe['buy-cci'] = ta.CCI(dataframe, timeperiod=self.buy_params['cci-period'])
        dataframe['sell-cci'] = ta.CCI(dataframe, timeperiod=self.sell_params['sell-cci-period'])

        # RSI
        dataframe['buy-rsi'] = ta.RSI(dataframe, timeperiod=self.buy_params['rsi-period'])
        dataframe['sell-rsi'] = ta.RSI(dataframe, timeperiod=self.sell_params['sell-rsi-period'])

        # KAMA - Kaufman Adaptive Moving Average
        dataframe['buy-kama-short'] = ta.KAMA(dataframe, timeperiod=self.buy_params['kama-short-period'])
        dataframe['buy-kama-long'] = ta.KAMA(dataframe, timeperiod=self.buy_params['kama-long-period'])
        dataframe['buy-kama-long-slope'] = (dataframe['buy-kama-long'] / dataframe['buy-kama-long'].shift())

        dataframe['sell-kama-short'] = ta.KAMA(dataframe, timeperiod=self.sell_params['sell-kama-short-period'])
        dataframe['sell-kama-long'] = ta.KAMA(dataframe, timeperiod=self.sell_params['sell-kama-long-period'])
        dataframe['sell-kama-long-slope'] = (dataframe['sell-kama-long'] / dataframe['sell-kama-long'].shift())

        return dataframe

    def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        conditions = []
        if self.buy_params['rsi-enabled']:
            conditions.append(dataframe['buy-rsi'] > self.buy_params['rsi-limit'])
        if self.buy_params['cci-enabled']:
            conditions.append(dataframe['buy-cci'] > self.buy_params['cci-limit'])
        if self.buy_params['kama-trigger'] == 'cross':
            conditions.append(dataframe['buy-kama-short'] > dataframe['buy-kama-long'])
        if self.buy_params['kama-trigger'] == 'slope':
            conditions.append(dataframe['buy-kama-long'] > 1)

        # Check that volume is not 0
        conditions.append(dataframe['volume'] > 0)

        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                'buy'] = 1

        return dataframe

    def populate_sell_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        conditions = []
        if self.sell_params['sell-rsi-enabled']:
            conditions.append(dataframe['sell-rsi'] < self.sell_params['sell-rsi-limit'])
        if self.sell_params['sell-cci-enabled']:
            conditions.append(dataframe['sell-cci'] < self.sell_params['sell-cci-limit'])
        if self.sell_params['sell-kama-trigger'] == 'cross':
            conditions.append(dataframe['sell-kama-short'] < dataframe['sell-kama-long'])
        if self.sell_params['sell-kama-trigger'] == 'slope':
            conditions.append(dataframe['sell-kama-long'] < 1)

        # Check that volume is not 0
        conditions.append(dataframe['volume'] > 0)

        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                'sell'] = 1

        return dataframe
    