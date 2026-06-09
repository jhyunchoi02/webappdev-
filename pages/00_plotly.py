import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="Global Top 10 Market Cap Dashboard",
    page_icon="📈",
    layout="wide"
)

# ------------------------------------------------------------
# 기본 기업 정보
# ------------------------------------------------------------
COMPANY_META = {
    "NVIDIA": {
        "ticker": "NVDA",
        "sector": "Semiconductors"
    },
    "Apple": {
        "ticker": "AAPL",
        "sector": "Consumer Electronics"
    },
    "Alphabet": {
        "ticker": "GOOG",
        "sector": "Internet Services"
    },
    "Microsoft": {
        "ticker": "MSFT",
        "sector": "Software / Cloud"
    },
    "Amazon": {
        "ticker": "AMZN",
        "sector": "E-Commerce / Cloud"
    },
    "TSMC": {
        "ticker": "TSM",
        "sector": "Semiconductors"
    },
    "Broadcom": {
        "ticker": "AVGO",
        "sector": "Semiconductors"
    },
    "Saudi Aramco": {
        "ticker": "2222.SR",
        "sector": "Energy"
    },
    "Tesla": {
        "ticker": "TSLA",
        "sector": "EV / Energy"
    },
    "Meta Platforms": {
        "ticker": "META",
        "sector": "Social / Advertising"
    },
}

# Yahoo Finance 환율 ticker
# 1단위 통화를 USD로 환산하기 위한 ticker입니다.
CURRENCY_TO_USD_TICKER = {
    "USD": None,
    "SAR": "SARUSD=X",
    "TWD": "TWDUSD=X",
    "KRW": "KRWUSD=X",
    "JPY": "JPYUSD=X",
    "EUR": "EURUSD=X",
    "GBP": "GBPUSD=X",
    "CNY": "CNYUSD=X",
    "HKD": "HKDUSD=X",
    "CHF": "CHFUSD=X",
}


# ------------------------------------------------------------
# 데이터 로딩 함수
# ------------------------------------------------------------
@st.cache_data(ttl=60 * 60)
def get_fx_rate_to_usd(currency: str) -> float:
    """
    특정 통화 1단위가 몇 USD인지 반환합니다.
    예: SARUSD=X, TWDUSD=X
    """
    currency = (currency or "USD").upper()

    if currency == "USD":
        return 1.0

    fx_ticker = CURRENCY_TO_USD_TICKER.get(currency)

    if not fx_ticker:
        return 1.0

    try:
        fx = yf.Ticker(fx_ticker).history(
            period="5d",
            interval="1d",
            auto_adjust=True
        )

        if fx.empty:
            return 1.0

        return float(fx["Close"].dropna().iloc[-1])

    except Exception:
        return 1.0


@st.cache_data(ttl=60 * 30)
def load_company_data(selected_companies: list, period: str = "1y"):
    """
    yfinance를 이용해 각 기업의 가격 데이터와 현재 시가총액을 가져옵니다.

    과거 시가총액은 다음 방식으로 근사합니다.

    과거 시가총액 =
    현재 시가총액 x 과거 조정종가 / 최근 조정종가

    주의:
    주식 수 변화, 자사주 매입, 증자, ADR 비율 변화 등은
    완전히 반영되지 않을 수 있습니다.
    """
    rows = []
    current_caps = []
    errors = []

    for company in selected_companies:
        ticker = COMPANY_META[company]["ticker"]
        sector = COMPANY_META[company]["sector"]

        try:
            tk = yf.Ticker(ticker)

            hist = tk.history(
                period=period,
                interval="1d",
                auto_adjust=True
            )

            if hist.empty or "Close" not in hist:
                errors.append(f"{company}({ticker}): 가격 데이터를 찾지 못했습니다.")
                continue

            fast = getattr(tk, "fast_info", {})

            info = {}
            try:
                info = tk.get_info()
            except Exception:
                info = {}

            current_market_cap = None

            try:
                if hasattr(fast, "get"):
                    current_market_cap = fast.get("market_cap")
            except Exception:
                current_market_cap = None

            if current_market_cap is None:
                current_market_cap = info.get("marketCap")

            if not current_market_cap:
                errors.append(f"{company}({ticker}): 현재 시가총액 데이터를 찾지 못했습니다.")
                continue

            currency = None

            try:
                if hasattr(fast, "get"):
                    currency = fast.get("currency")
            except Exception:
                currency = None

            currency = currency or info.get("currency") or "USD"
            fx = get_fx_rate_to_usd(currency)

            close = hist["Close"].dropna()
            last_close = float(close.iloc[-1])

            current_cap_usd = float(current_market_cap) * fx
            cap_usd = current_cap_usd * (close / last_close)

            df = pd.DataFrame({
                "Date": close.index.tz_localize(None),
                "Company": company,
                "Ticker": ticker,
                "Sector": sector,
                "Market Cap USD": cap_usd.values,
                "Market Cap Trillion USD": cap_usd.values / 1e12,
                "Price": close.values,
                "Currency": currency,
            })

            rows.append(df)

            current_caps.append({
                "Company": company,
                "Ticker": ticker,
                "Sector": sector,
                "Current Market Cap USD": current_cap_usd,
                "Current Market Cap Trillion USD": current_cap_usd / 1e12,
                "Currency": currency,
                "FX to USD": fx,
            })

        except Exception as e:
            errors.append(f"{company}({ticker}): {e}")

    data = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

    caps = (
        pd.DataFrame(current_caps)
        .sort_values("Current Market Cap USD", ascending=False)
        if current_caps
        else pd.DataFrame()
    )

    return data, caps, errors


# ------------------------------------------------------------
# 분석용 데이터 생성 함수
# ------------------------------------------------------------
def calculate_returns(data: pd.DataFrame) -> pd.DataFrame:
    returns = (
        data.sort_values("Date")
        .groupby("Company")
        .agg(
            first_cap=("Market Cap USD", "first"),
            last_cap=("Market Cap USD", "last"),
            sector=("Sector", "first"),
            ticker=("Ticker", "first")
        )
        .reset_index()
    )

    returns["Return %"] = (
        returns["last_cap"] / returns["first_cap"] - 1
    ) * 100

    return returns.sort_values("Return %", ascending=False)


def calculate_volatility(data: pd.DataFrame) -> pd.DataFrame:
    vol_data = data.sort_values(["Company", "Date"]).copy()

    vol_data["Daily Return"] = (
        vol_data
        .groupby("Company")["Market Cap USD"]
        .pct_change()
    )

    vol_df = (
        vol_data
        .groupby("Company")
        .agg(
            daily_volatility=("Daily Return", "std"),
            sector=("Sector", "first"),
            ticker=("Ticker", "first")
        )
        .reset_index()
    )

    vol_df["Annualized Volatility %"] = (
        vol_df["daily_volatility"] * (252 ** 0.5) * 100
    )

    return vol_df.sort_values("Annualized Volatility %", ascending=False)


def add_range_selector(fig):
    fig.update_xaxes(
        rangeslider_visible=True,
        rangeselector=dict(
            buttons=list([
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=3, label="3M", step="month", stepmode="backward"),
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="1Y", step="year", stepmode="backward"),
                dict(step="all", label="ALL")
            ])
        )
    )

    return fig


# ------------------------------------------------------------
# 사이드바
# ------------------------------------------------------------
st.sidebar.title("📊 대시보드 설정")

period = st.sidebar.selectbox(
    "조회 기간",
    ["1y", "6mo", "2y", "5y"],
    index=0
)

selected_companies = st.sidebar.multiselect(
    "표시할 기업",
    options=list(COMPANY_META.keys()),
    default=list(COMPANY_META.keys())
)

plotly_theme = st.sidebar.selectbox(
    "Plotly 테마",
    ["plotly_white", "plotly", "plotly_dark", "ggplot2", "seaborn", "simple_white"],
    index=0
)

show_points = st.sidebar.checkbox(
    "라인 차트에 데이터 포인트 표시",
    value=False
)

show_annotations = st.sidebar.checkbox(
    "선택 기업 최고점 주석 표시",
    value=False
)

annotation_company = st.sidebar.selectbox(
    "주석 표시 기업",
    options=selected_companies if selected_companies else list(COMPANY_META.keys()),
    index=0
)

st.sidebar.divider()

st.sidebar.markdown("### 기본 기업 목록")
for company, meta in COMPANY_META.items():
    st.sidebar.caption(f"{company}: {meta['ticker']} / {meta['sector']}")


# ------------------------------------------------------------
# 메인 화면
# ------------------------------------------------------------
st.title("📈 글로벌 시가총액 Top 10 대시보드")
st.caption(
    "Yahoo Finance 데이터, yfinance, Plotly를 이용한 Streamlit Cloud용 대시보드"
)

if not selected_companies:
    st.error("왼쪽 사이드바에서 최소 1개 이상의 기업을 선택하세요.")
    st.stop()

data, caps, errors = load_company_data(selected_companies, period)

if errors:
    with st.expander("데이터 조회 알림", expanded=False):
        for error in errors:
            st.warning(error)

if data.empty:
    st.error("표시할 데이터가 없습니다. 잠시 후 다시 시도하거나 ticker를 확인하세요.")
    st.stop()

returns = calculate_returns(data)
volatility = calculate_volatility(data)

latest = (
    data
    .sort_values("Date")
    .groupby("Company")
    .tail(1)
)

# ------------------------------------------------------------
# KPI 영역
