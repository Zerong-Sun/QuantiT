"""Explicit definitions: statistical periods are never release timestamps."""
from __future__ import annotations

FRENCH_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip"
FRENCH_PAGE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5_factors_2x3.html"
SERIES = {}


def add(key, name, region, frequency, unit, provider, dataset, field="", transform="level", note="", kind="macro", source_url=""):
    SERIES[key] = dict(id=key, name=name, region=region, frequency=frequency, unit=unit,
                       provider=provider, dataset=dataset, field=field, transform=transform,
                       note=note, kind=kind, source_url=source_url)


for key, name, code, freq, unit, transform, note in [
    ("us_payroll", "美国新增非农就业", "PAYEMS", "M", "千人", "diff", "季调就业人数的逐月差值；不是就业总人数，也不是市场预期差。"),
    ("us_unemployment", "美国失业率", "UNRATE", "M", "%", "level", "季调失业率。"),
    ("us_cpi", "美国 CPI 同比", "CPIAUCNS", "M", "%", "yoy", "未季调 CPI 指数相对上年同月的变化率。"),
    ("us_core_cpi", "美国核心 CPI 同比", "CPILFESL", "M", "%", "yoy", "剔除食品和能源；由季调指数计算同比。"),
    ("us_fed_rate", "美国联邦基金有效利率", "FEDFUNDS", "M", "%", "level", "月均有效利率，不是联储目标区间上限。"),
    ("us_treasury10", "美国 10 年期国债收益率", "GS10", "M", "%", "level", "月均收益率，不是债券价格或当日盘中报价。"),
    ("us_gdp", "美国实际 GDP 环比折年率", "A191RL1Q225SBEA", "Q", "%", "level", "季度实际 GDP 季调环比折年率，不能与中国累计同比直接比较。"),
    ("us_pce", "美国 PCE 价格同比", "PCEPI", "M", "%", "yoy", "由季调 PCE 价格指数计算同比。"),
]:
    add(key, name, "US", freq, unit, "FRED", code, transform=transform, note=note,
        source_url=f"https://fred.stlouisfed.org/series/{code}")

for key, name, report, field, freq, page, note in [
    ("cn_cpi", "中国 CPI 同比", "CPI", "NATIONAL_SAME", "M", "cpi", "全国居民消费价格同比变化。"),
    ("cn_ppi", "中国 PPI 同比", "PPI", "BASE_SAME", "M", "ppi", "工业生产者出厂价格同比变化。"),
    ("cn_pmi", "中国制造业 PMI", "PMI", "MAKE_INDEX", "M", "pmi", "官方制造业采购经理指数，50 为荣枯分界。"),
    ("cn_nonmanufacturing", "中国非制造业商务活动指数", "PMI", "NMAKE_INDEX", "M", "pmi", "官方非制造业商务活动指数，50 为荣枯分界。"),
    ("cn_m2", "中国 M2 同比", "CURRENCY_SUPPLY", "BASIC_CURRENCY_SAME", "M", "hbgyl", "广义货币余额同比变化。"),
    ("cn_gdp_ytd", "中国 GDP 累计同比", "GDP", "SUM_SAME", "Q", "gdp", "当年年初至本季度累计同比；不是单季度同比或环比折年率。"),
]:
    add(key, name, "CN", freq, "指数" if report == "PMI" else "%", "东方财富宏观数据", f"RPT_ECONOMY_{report}",
        field, note=note + " 经东方财富转载统计部门/央行数据，采用当前修订值。",
        source_url=f"https://data.eastmoney.com/cjsj/{page}.html")

for key, name, code, note in [
    ("cn_gdp_annual", "中国实际 GDP 增长（年度长历史）", "NY.GDP.MKTP.KD.ZG", "世界银行年度实际 GDP 增长率；与季度累计数据独立显示，不拼接。"),
    ("cn_cpi_annual", "中国消费价格通胀（年度）", "FP.CPI.TOTL.ZG", "世界银行年度通胀率；不是某个月 CPI 同比。"),
]:
    add(key, name, "CN", "Y", "%", "World Bank WDI", code, note=note,
        source_url=f"https://data.worldbank.org/indicator/{code}?locations=CN")

for key, name, field, note in [
    ("ff_market", "市场超额收益 · Mkt−RF", "Mkt-RF", "美国股票市场收益减无风险利率。"),
    ("ff_size", "规模因子 · SMB", "SMB", "小市值组合减大市值组合收益。"),
    ("ff_value", "价值因子 · HML", "HML", "高账面市值比组合减低账面市值比组合收益。"),
    ("ff_profitability", "盈利因子 · RMW", "RMW", "高经营盈利组合减低经营盈利组合收益。"),
    ("ff_investment", "投资因子 · CMA", "CMA", "保守投资组合减激进投资组合收益。"),
]:
    add(key, name, "US", "M", "%", "Kenneth R. French Data Library", "ff5", field, kind="factor",
        note=note + " 月度研究因子收益，未扣本账户交易费用。2025 年起采用 CRSP CIZ 数据方法；历史值可能修订。",
        source_url=FRENCH_PAGE)

for name, label in [
    ("alpha158_lgbm_h1", "LightGBM 1 日"),
    ("alpha158_lgbm_h5", "LightGBM 5 日"),
    ("alpha158_lgbm_h10", "LightGBM 10 日"),
    ("momentum_20", "20 日动量"),
    ("momentum_60", "60 日动量"),
]:
    add(f"local_{name}", f"{label} · 样本外 Rank IC", "CN", "D", "IC", "本地冻结研究实验",
        "local", name, kind="local_factor",
        note="逐交易日预测排序与已成熟远期收益的横截面 Spearman 相关；不属于因子收益率。固定股票池，历史长度受真实实验样本限制。",
        source_url="/research")

NEWS_SOURCES = {
    "fed": {"name": "美联储公告", "url": "https://www.federalreserve.gov/feeds/press_all.xml", "region": "US"},
    "china": {"name": "中新网财经", "url": "https://www.chinanews.com.cn/rss/finance.xml", "region": "CN"},
    "world": {"name": "BBC 商业新闻", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "region": "GLOBAL"},
}
