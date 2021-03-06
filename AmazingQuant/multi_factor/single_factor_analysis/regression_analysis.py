# -*- coding: utf-8 -*-

# ------------------------------
# @Time    : 2020/3/31
# @Author  : gao
# @File    : regression_analysis.py
# @Project : AmazingQuant
# ------------------------------

"""
回归法分析
以流通市值平方根或者市值的倒数为权重做WLS,
将因子T期的因子暴露与T+1期股票收益，加权最小二乘法估计因子收益率，得到T-1个数据的因子收益率序列。

(1)单因子回归方程系数T检验值的绝对值均值，通常该值大于2认为是理想的结果，表明因子对收益率的影响显著性程度较高；
(2)单因子回归方程系数T检验值绝对值序列大于2的占比，该值用以解释在测试时间范围内，因子显著性程度的分布特征；
(3)年化因子收益率，该值表明因子对收益率的贡献程度，取年化的原因在于可以与策略年化收益率有个较为直观的比较；
(4)年化波动率,日收益波动率,月收益波动率，该值表明因子对收益率贡献的波动程度，取年化的原因同样在于可以与策略年化收益的波动率有个较为直观的比较；
(5)日收益率分布,月收益率分布,正收益天数,负收益天数,日胜率,月胜率,峰度,偏度
(6)最大回撤
(7)夏普比率,calmar比率,特雷诺比率,索提诺比率
(8)beta,跟踪误差,信息比率,
(9)因子自稳定性系数（FactorStabilityCoeff），该值检验因子收益率的稳定性
"""
#
# m = 1 + 28 + 1，单因子，28行业，流通市值
# m个因子, n只股票
# f  ---- m*1
# x’-----m*n
# W-----n*n
# x----- n*m
# R-----n*1

import statsmodels.api as sm
import numpy as np
import pandas as pd

from AmazingQuant.constant import LocalDataFolderName, RightsAdjustment
from AmazingQuant.config.local_data_path import LocalDataPath
from AmazingQuant.data_center.api_data.get_data import get_local_data
from AmazingQuant.data_center.api_data.get_kline import GetKlineData
from AmazingQuant.data_center.api_data.get_index_class import GetIndexClass
from AmazingQuant.data_center.api_data.get_share import GetShare


class RegressionAnalysis(object):
    def __init__(self, factor, factor_name, market_close_data):
        self.factor = factor
        self.factor_name = factor_name

        market_data = market_close_data.reindex(factor.index).reindex(factor.columns, axis=1)
        self.stock_return = market_data.pct_change()

        # 因子收益率，单利，复利
        self.factor_return = pd.DataFrame(index=self.factor.index, columns=['cumsum', 'cumprod'])
        self.factor_return_daily = None

        # 单因子检测的T值
        self.factor_t_value = None
        # 单因子检测的T值的统计值，'t_value_mean': 绝对值均值, 't_value_greater_two':绝对值序列大于2的占比
        self.factor_t_value_statistics = None

    def cal_factor_return(self, method='float_value_inverse'):
        """
        method = {‘float_value_inverse’, ‘float_value_square_root’}
        :param method:
        :return:
        """
        index_class_obj = GetIndexClass()
        index_class_obj.get_index_class()
        index_class_obj.get_zero_index_class()

        share_data_obj = GetShare()
        share_data = share_data_obj.get_share('float_a_share_value')

        index_list = self.factor.index
        factor_return_daily = {}
        factor_t_value_dict = {}
        for index in range(self.factor.shape[0]):
            stock_return = self.stock_return.iloc[index].dropna()
            factor_data = self.factor.iloc[index].dropna()

            stock_list = list(set(stock_return.index).intersection(set(factor_data.index)))
            stock_return = stock_return[stock_list].sort_index()
            print(index_list[index])
            index_class_in_date = index_class_obj.get_index_class_in_date(index_list[index]).reindex(stock_list).sort_index()

            share_data_in_date = share_data.loc[index_list[index]].reindex(stock_list).dropna()
            share_data_in_date = pd.DataFrame({'float_a_share_value': share_data_in_date[stock_list].sort_index()})
            factor_data = pd.DataFrame({self.factor_name: factor_data[stock_list].sort_index()})

            x = sm.add_constant(pd.concat([index_class_in_date, factor_data, share_data_in_date], axis=1))
            if stock_return.empty:
                factor_return_daily[index_list[index]] = None
                factor_t_value_dict[index_list[index]] = None
                continue
            wls_model = None
            if method == 'float_value_inverse':
                weights = (1. / share_data_in_date['float_a_share_value'])
                weights[np.isinf(weights)] = 0
                wls_model = sm.WLS(stock_return, x, weights=weights)
            elif method == 'float_value_square_root':
                wls_model = sm.WLS(stock_return, x, weights=share_data_in_date['float_a_share_value'].values ** 0.5)

            if wls_model is None:
                factor_return_daily[index_list[index]] = None
                factor_t_value_dict[index_list[index]] = None
                continue
            else:
                results = wls_model.fit()
                factor_return_daily[index_list[index]] = results.params[self.factor_name]
                factor_t_value_dict[index_list[index]] = results.tvalues[self.factor_name]

        self.factor_t_value = pd.Series(factor_t_value_dict)
        self.factor_return_daily = pd.Series(factor_return_daily)
        self.factor_return['cumsum'] = self.factor_return_daily.cumsum() + 1
        self.factor_return['cumprod'] = (self.factor_return_daily.add(1)).cumprod()

    def cal_t_value_statistics(self):
        t_value_abs = self.factor_t_value.abs()
        t_value_greater_two = t_value_abs[t_value_abs > 2].count()/(t_value_abs.count())
        t_value_mean = self.factor_t_value.mean()
        self.factor_t_value_statistics = pd.Series({'t_value_mean': t_value_mean,
                                                    't_value_greater_two': t_value_greater_two})


if __name__ == '__main__':
    path = LocalDataPath.path + LocalDataFolderName.FACTOR.value + '/'
    factor_ma5 = get_local_data(path, 'factor_ma5.h5')
    market_close_data = GetKlineData().cache_all_stock_data(dividend_type=RightsAdjustment.BACKWARD.value,
                                                            field=['close'])['close']
    regression_analysis_obj = RegressionAnalysis(factor_ma5, 'factor_ma5', market_close_data)
    regression_analysis_obj.cal_factor_return('float_value_inverse')
    regression_analysis_obj.cal_t_value_statistics()

