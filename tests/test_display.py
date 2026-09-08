"""Display labels: HK / CN / futures show 公司名字（股票代码）."""

from quantit.markets.display import display_label, lookup_name


class TestDisplayLabel:
    def test_hk_uses_name_and_code(self) -> None:
        assert display_label("hk", "0700.HK") == "Tencent（0700.HK）"
        assert display_label("hk", "700") == "Tencent（0700.HK）"

    def test_cn_uses_name_and_code(self) -> None:
        assert display_label("cn", "600519.SS") == "Kweichow Moutai（600519.SS）"
        assert display_label("cn", "510300") == "CSI 300 ETF（510300.SS）"

    def test_futures_uses_name_and_code(self) -> None:
        assert display_label("fut", "IF2509", name="沪深300股指") == "沪深300股指（IF2509）"
        assert display_label("futures", "CU2509", name="沪铜") == "沪铜（CU2509）"

    def test_us_stays_ticker_only(self) -> None:
        assert display_label("us", "AAPL") == "AAPL"
        assert display_label("us", "AAPL", name="Apple") == "AAPL"
        assert display_label("us_book", "JNJ") == "JNJ"

    def test_book_ids_follow_venue_labels(self) -> None:
        assert display_label("hk_theme", "0700.HK") == "Tencent（0700.HK）"
        assert display_label("cn_etf", "510300.SS") == "CSI 300 ETF（510300.SS）"

    def test_unknown_name_falls_back_to_symbol(self) -> None:
        assert display_label("hk", "99999.HK") == "99999.HK"
        assert display_label("fut", "IF2509") == "IF2509"

    def test_lookup_normalizes_cn_and_hk(self) -> None:
        assert lookup_name("hk", "1810") == "Xiaomi"
        assert lookup_name("cn", "000333") == "Midea Group"
        assert lookup_name("cl", "SH600519") == "Kweichow Moutai"
