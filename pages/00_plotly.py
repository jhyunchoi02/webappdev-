import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px

st.set_page_config(
    page_title="Global Top 10 Market Cap Dashboard",
    page_icon="📈",
    layout="wide"
)

# 글로벌 시가총액 Top 10 기본 목록
# Yahoo Finance에서 조회 가능한 ticker를 사용합니다.
DEFAULT_COMPANIES = {
    "NVIDIA": "NVDA",
    "Apple": "AAPL",
    "Alphabet": "GOOG",
    "Microsoft": "MSFT",
    "Amazon": "AMZN",
    "TSMC": "TSM",
    "Broadcom": "AVGO",
    "Saudi Aramco": "2222.SR",
    "Tesla": "TSLA",
    "Meta Platforms": "META",
}

# 통화를 USD로 변환하기 위한 Yahoo Finance 환율 ticker
CURRENCY_TO_USD_TICKER = {
    "USD": None,
    "SAR": "SARUSD=X",
    "TWD": "TWDUSD=X",
}


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
def load_company_data(companies: dict, period: str = "1y"):
    """
    yfinance를 이용해 각 기업의 가격 데이터와 현재 시가총액을 가져옵니다.

    과거 시가총액은 다음 방식으로 근사합니다.

    과거 시가총액 =
    현재 시가총액 x 과거 조정종가 / 최근 조정종가

    단, 주식 수 변화, 자사주 매입, 증자, ADR 비율 변화 등은 완전히 반영되지 않을 수 있습니다.
    """
    rows = []
    current_caps = []
    errors = []

    for name, ticker in companies.items():
        try:
            tk = yf.Ticker(ticker)

            hist = tk.history(
                period=period,
                interval="1d",
                auto_adjust=True
            )

            if hist.empty or "Close" not in hist:
                errors.append(f"{name}({ticker}): 가격 데이터를 찾지 못했습니다.")
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
                errors.append(f"{name}({ticker}): 현재 시가총액 데이터를 찾지 못했습니다.")
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
                "Company": name,
                "Ticker": ticker,
                "Market Cap USD": cap_usd.values,
                "Market Cap Trillion USD": cap_usd.values / 1e12,
                "Price": close.values,
                "Currency": currency,
            })

            rows.append(df)

            current_caps.append({
                "Company": name,
                "Ticker": ticker,
                "Current Market Cap USD": current_cap_usd,
                "Current Market Cap Trillion USD": current_cap_usd / 1e12,
                "Currency": currency,
                "FX to USD": fx,
            })

        except Exception as e:
            errors.append(f"{name}({ticker}): {e}")

    data = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

    caps = (
        pd.DataFrame(current_caps)
        .sort_values("Current Market Cap USD", ascending=False)
        if current_caps
        else pd.DataFrame()
    )

    return data, caps, errors


st.title("📈 글로벌 시가총액 Top 10 — 최근 1년 변화")
st.caption("Yahoo Finance 데이터, yfinance, Plotly를 이용한 Streamlit Cloud용 주식 대시보드")

with st.sidebar:
    st.header("설정")

    period = st.selectbox(
        "조회 기간",
        ["1y", "6mo", "2y", "5y"],
        index=0
    )

    normalize = st.checkbox(
        "시작일=100 지수로 보기",
        value=False
    )

    show_points = st.checkbox(
        "데이터 포인트 표시",
        value=False
    )

    selected = st.multiselect(
        "표시할 기업",
        options=list(DEFAULT_COMPANIES.keys()),
        default=list(DEFAULT_COMPANIES.keys())
    )

    st.divider()

    st.markdown("### 기본 티커")
    st.code(
        "\n".join([f"{company}: {ticker}" for company, ticker in DEFAULT_COMPANIES.items()])
    )

companies = {
    company: DEFAULT_COMPANIES[company]
    for company in selected
}

data, caps, errors = load_company_data(companies, period)

if errors:
    with st.expander("데이터 조회 알림", expanded=False):
        for error in errors:
            st.warning(error)

if data.empty:
    st.error("표시할 데이터가 없습니다. 잠시 후 다시 시도하거나 ticker를 확인하세요.")
    st.stop()

latest = (
    data
    .sort_values("Date")
    .groupby("Company")
    .tail(1)
)

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "기업 수",
    f"{latest['Company'].nunique():,}"
)

col2.metric(
    "최대 시가총액",
    f"${latest['Market Cap Trillion USD'].max():.2f}T"
)

col3.metric(
    "합산 시가총액",
    f"${latest['Market Cap Trillion USD'].sum():.2f}T"
)

col4.metric(
    "최근 거래일",
    str(latest["Date"].max().date())
)

plot_df = data.copy()

y_col = "Market Cap Trillion USD"
y_title = "시가총액, 조 달러 USD"

if normalize:
    plot_df = plot_df.sort_values("Date")
    first_values = plot_df.groupby("Company")["Market Cap USD"].transform("first")
    plot_df["Index"] = plot_df["Market Cap USD"] / first_values * 100

    y_col = "Index"
    y_title = "시작일=100 지수"

fig = px.line(
    plot_df,
    x="Date",
    y=y_col,
    color="Company",
    markers=show_points,
    hover_data={
        "Ticker": True,
        "Market Cap Trillion USD": ":.3f",
        "Price": ":.2f",
        "Currency": True,
    },
    title=f"글로벌 시가총액 Top 10 최근 {period} 변화"
)

fig.update_layout(
    hovermode="x unified",
    legend_title_text="기업",
    xaxis_title="날짜",
    yaxis_title=y_title,
    height=650,
)

st.plotly_chart(fig, use_container_width=True)

st.subheader("현재 시가총액 순위")

if not caps.empty:
    show_caps = caps.copy()

    show_caps["Current Market Cap USD"] = show_caps["Current Market Cap USD"].map(
        lambda x: f"${x / 1e12:.3f}T"
    )

    show_caps["Current Market Cap Trillion USD"] = show_caps[
        "Current Market Cap Trillion USD"
    ].map(
        lambda x: f"{x:.3f}"
    )

    show_caps["FX to USD"] = show_caps["FX to USD"].map(
        lambda x: f"{x:.6f}"
    )

    st.dataframe(
        show_caps,
        use_container_width=True,
        hide_index=True
    )

st.info(
    "계산 방식: yfinance의 현재 시가총액을 기준값으로 사용하고, "
    "최근 기간의 조정종가 변화율을 곱해 과거 시가총액을 근사했습니다. "
    "따라서 유상증자, 자사주 매입, 주식분할, ADR 비율 변화 등 주식 수 변화는 "
    "완전히 반영되지 않을 수 있습니다."
)

csv = data.to_csv(index=False).encode("utf-8-sig")

st.download_button(
    label="CSV 다운로드",
    data=csv,
    file_name="global_top10_marketcap_history.csv",
    mime="text/csv"
)
