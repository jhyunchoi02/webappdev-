import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px

st.set_page_config(
    page_title="Global Top 10 Market Cap Dashboard",
    page_icon="📈",
    layout="wide"
)

# ------------------------------------------------------------
# 기업 정보
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
# 유틸 함수
# ------------------------------------------------------------
@st.cache_data(ttl=60 * 60)
def get_fx_rate_to_usd(currency: str) -> float:
    currency = (currency or "USD").upper()

    if currency == "USD":
        return 1.0

    fx_ticker = CURRENCY_TO_USD_TICKER.get(currency)

    if fx_ticker is None:
        return 1.0

    try:
        fx = yf.download(
            fx_ticker,
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=True
        )

        if fx.empty:
            return 1.0

        return float(fx["Close"].dropna().iloc[-1])

    except Exception:
        return 1.0


def safe_get_fast_info_value(fast_info, key):
    try:
        if hasattr(fast_info, "get"):
            value = fast_info.get(key)
        else:
            value = fast_info[key]

        return value

    except Exception:
        return None


@st.cache_data(ttl=60 * 30)
def load_company_data(selected_companies, period):
    rows = []
    current_caps = []
    errors = []

    selected_meta = {
        company: COMPANY_META[company]
        for company in selected_companies
    }

    tickers = [
        meta["ticker"]
        for meta in selected_meta.values()
    ]

    try:
        price_data = yf.download(
            tickers=tickers,
            period=period,
            interval="1d",
            auto_adjust=True,
            group_by="ticker",
            progress=False,
            threads=True
        )
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), [f"가격 데이터 전체 다운로드 실패: {e}"]

    for company, meta in selected_meta.items():
        ticker = meta["ticker"]
        sector = meta["sector"]

        try:
            if len(tickers) == 1:
                hist = price_data.copy()
            else:
                if ticker not in price_data.columns.get_level_values(0):
                    errors.append(f"{company}({ticker}): 가격 데이터 없음")
                    continue

                hist = price_data[ticker].copy()

            if hist.empty or "Close" not in hist.columns:
                errors.append(f"{company}({ticker}): Close 가격 없음")
                continue

            close = hist["Close"].dropna()

            if close.empty:
                errors.append(f"{company}({ticker}): 유효한 종가 데이터 없음")
                continue

            tk = yf.Ticker(ticker)
            fast = tk.fast_info

            market_cap = safe_get_fast_info_value(fast, "market_cap")
            currency = safe_get_fast_info_value(fast, "currency") or "USD"

            # market_cap이 없으면 last_price * shares로 보조 계산
            if market_cap is None:
                last_price = safe_get_fast_info_value(fast, "last_price")
                shares = safe_get_fast_info_value(fast, "shares")

                if last_price is not None and shares is not None:
                    market_cap = float(last_price) * float(shares)

            if market_cap is None:
                errors.append(f"{company}({ticker}): 시가총액 데이터를 찾지 못해 제외")
                continue

            fx = get_fx_rate_to_usd(currency)

            last_close = float(close.iloc[-1])
            current_cap_usd = float(market_cap) * fx

            # 과거 시가총액 근사
            market_cap_series = current_cap_usd * close / last_close

            temp = pd.DataFrame({
                "Date": close.index.tz_localize(None),
                "Company": company,
                "Ticker": ticker,
                "Sector": sector,
                "Market Cap USD": market_cap_series.values,
                "Market Cap Trillion USD": market_cap_series.values / 1e12,
                "Price": close.values,
                "Currency": currency
            })

            rows.append(temp)

            current_caps.append({
                "Company": company,
                "Ticker": ticker,
                "Sector": sector,
                "Current Market Cap USD": current_cap_usd,
                "Current Market Cap Trillion USD": current_cap_usd / 1e12,
                "Currency": currency,
                "FX to USD": fx
            })

        except Exception as e:
            errors.append(f"{company}({ticker}) 처리 실패: {e}")

    data = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

    caps = (
        pd.DataFrame(current_caps)
        .sort_values("Current Market Cap USD", ascending=False)
        if current_caps
        else pd.DataFrame()
    )

    return data, caps, errors


def calculate_returns(data):
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


def calculate_volatility(data):
    temp = data.sort_values(["Company", "Date"]).copy()

    temp["Daily Return"] = (
        temp.groupby("Company")["Market Cap USD"].pct_change()
    )

    vol = (
        temp.groupby("Company")
        .agg(
            daily_volatility=("Daily Return", "std"),
            sector=("Sector", "first"),
            ticker=("Ticker", "first")
        )
        .reset_index()
    )

    vol["Annualized Volatility %"] = (
        vol["daily_volatility"] * (252 ** 0.5) * 100
    )

    return vol.sort_values("Annualized Volatility %", ascending=False)


def add_range_selector(fig):
    fig.update_xaxes(
        rangeslider_visible=True,
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=3, label="3M", step="month", stepmode="backward"),
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="1Y", step="year", stepmode="backward"),
                dict(step="all", label="ALL")
            ]
        )
    )

    return fig


# ------------------------------------------------------------
# 사이드바
# ------------------------------------------------------------
st.sidebar.title("📊 설정")

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
    "라인 차트에 점 표시",
    value=False
)

st.sidebar.divider()
st.sidebar.caption("처음 로딩은 Yahoo Finance 응답 속도에 따라 시간이 걸릴 수 있습니다.")


# ------------------------------------------------------------
# 메인
# ------------------------------------------------------------
st.title("📈 글로벌 시가총액 Top 10 대시보드")
st.caption("yfinance + Plotly + Streamlit Cloud용 대시보드")

if not selected_companies:
    st.error("왼쪽에서 최소 1개 이상의 기업을 선택하세요.")
    st.stop()

with st.spinner("Yahoo Finance에서 데이터를 불러오는 중입니다. 잠시만 기다려주세요..."):
    data, caps, errors = load_company_data(selected_companies, period)

if errors:
    with st.expander("데이터 조회 알림", expanded=False):
        for error in errors:
            st.warning(error)

if data.empty:
    st.error("표시할 데이터가 없습니다.")
    st.markdown("""
가능한 원인:

1. Yahoo Finance 응답이 일시적으로 실패했습니다.
2. Streamlit Cloud에서 특정 ticker가 느리게 응답합니다.
3. `Saudi Aramco(2222.SR)` 같은 해외 거래소 ticker가 실패했을 수 있습니다.

해결 방법:

- 새로고침해보세요.
- 사이드바에서 `Saudi Aramco`를 제외하고 다시 시도해보세요.
- 조회 기간을 `6mo`로 줄여보세요.
""")
    st.stop()

returns = calculate_returns(data)
volatility = calculate_volatility(data)

latest = (
    data.sort_values("Date")
    .groupby("Company")
    .tail(1)
)

# ------------------------------------------------------------
# KPI
# ------------------------------------------------------------
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

st.info(
    "과거 시가총액은 현재 시가총액과 주가 변화율을 이용한 추정값입니다. "
    "실제 과거 발행주식 수 변화를 완전히 반영하지는 않습니다."
)

# ------------------------------------------------------------
# 탭
# ------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "① 시가총액 추이",
    "② 현재 순위와 비중",
    "③ 수익률과 변동성",
    "④ 상관관계"
])


# ------------------------------------------------------------
# 탭 1
# ------------------------------------------------------------
with tab1:
    st.subheader("시가총액 추이")

    fig = px.line(
        data,
        x="Date",
        y="Market Cap Trillion USD",
        color="Company",
        markers=show_points,
        hover_data={
            "Ticker": True,
            "Sector": True,
            "Market Cap Trillion USD": ":.3f",
            "Price": ":.2f",
            "Currency": True
        },
        title=f"최근 {period} 시가총액 변화",
        template=plotly_theme
    )

    fig.update_layout(
        hovermode="x unified",
        xaxis_title="날짜",
        yaxis_title="시가총액, 조 달러 USD",
        legend_title_text="기업",
        height=650
    )

    fig = add_range_selector(fig)

    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("시작일=100 정규화 차트")

    norm = data.sort_values("Date").copy()
    first_values = norm.groupby("Company")["Market Cap USD"].transform("first")
    norm["Index"] = norm["Market Cap USD"] / first_values * 100

    norm_fig = px.line(
        norm,
        x="Date",
        y="Index",
        color="Company",
        markers=show_points,
        hover_data={
            "Ticker": True,
            "Sector": True,
            "Index": ":.2f"
        },
        title="시작일=100 기준 상대 변화",
        template=plotly_theme
    )

    norm_fig.update_layout(
        hovermode="x unified",
        xaxis_title="날짜",
        yaxis_title="시작일=100 지수",
        legend_title_text="기업",
        height=600
    )

    norm_fig = add_range_selector(norm_fig)

    st.plotly_chart(norm_fig, use_container_width=True)


# ------------------------------------------------------------
# 탭 2
# ------------------------------------------------------------
with tab2:
    st.subheader("현재 시가총액 순위")

    if caps.empty:
        st.warning("현재 시가총액 데이터를 표시할 수 없습니다.")
    else:
        bar_fig = px.bar(
            caps,
            x="Company",
            y="Current Market Cap Trillion USD",
            color="Sector",
            text="Current Market Cap Trillion USD",
            title="현재 시가총액 순위",
            template=plotly_theme
        )

        bar_fig.update_traces(
            texttemplate="%{text:.2f}T",
            textposition="outside"
        )

        bar_fig.update_layout(
            xaxis_title="기업",
            yaxis_title="시가총액, 조 달러 USD",
            height=550
        )

        st.plotly_chart(bar_fig, use_container_width=True)

        st.divider()

        st.subheader("시가총액 비중 Treemap")

        tree_fig = px.treemap(
            caps,
            path=["Sector", "Company"],
            values="Current Market Cap Trillion USD",
            color="Sector",
            title="산업군별 현재 시가총액 비중",
            template=plotly_theme
        )

        tree_fig.update_traces(
            texttemplate="<b>%{label}</b><br>%{value:.2f}T"
        )

        tree_fig.update_layout(height=650)

        st.plotly_chart(tree_fig, use_container_width=True)

        st.divider()

        st.subheader("현재 시가총액 데이터")

        show_caps = caps.copy()

        show_caps["Current Market Cap USD"] = show_caps[
            "Current Market Cap USD"
        ].map(lambda x: f"${x / 1e12:.3f}T")

        show_caps["Current Market Cap Trillion USD"] = show_caps[
            "Current Market Cap Trillion USD"
        ].map(lambda x: f"{x:.3f}")

        show_caps["FX to USD"] = show_caps["FX to USD"].map(
            lambda x: f"{x:.6f}"
        )

        st.dataframe(
            show_caps,
            use_container_width=True,
            hide_index=True
        )


# ------------------------------------------------------------
# 탭 3
# ------------------------------------------------------------
with tab3:
    st.subheader("최근 기간 변화율 순위")

    return_fig = px.bar(
        returns,
        x="Company",
        y="Return %",
        color="Return %",
        text="Return %",
        title=f"최근 {period} 시가총액 변화율",
        template=plotly_theme,
        color_continuous_scale="RdYlGn"
    )

    return_fig.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="outside"
    )

    return_fig.update_layout(
        xaxis_title="기업",
        yaxis_title="변화율, %",
        height=550
    )

    st.plotly_chart(return_fig, use_container_width=True)

    st.divider()

    st.subheader("연율화 변동성")

    vol_fig = px.bar(
        volatility,
        x="Company",
        y="Annualized Volatility %",
        color="Annualized Volatility %",
        text="Annualized Volatility %",
        title="기업별 연율화 변동성",
        template=plotly_theme,
        color_continuous_scale="OrRd"
    )

    vol_fig.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="outside"
    )

    vol_fig.update_layout(
        xaxis_title="기업",
        yaxis_title="연율화 변동성, %",
        height=550
    )

    st.plotly_chart(vol_fig, use_container_width=True)


# ------------------------------------------------------------
# 탭 4
# ------------------------------------------------------------
with tab4:
    st.subheader("일간 변화율 상관관계")

    pivot_returns = (
        data.pivot(index="Date", columns="Company", values="Market Cap USD")
        .pct_change()
        .dropna()
    )

    if pivot_returns.shape[1] >= 2:
        corr = pivot_returns.corr()

        heat_fig = px.imshow(
            corr,
            text_auto=".2f",
            color_continuous_scale="RdBu_r",
            zmin=-1,
            zmax=1,
            title="기업별 일간 시가총액 변화율 상관관계",
            template=plotly_theme
        )

        heat_fig.update_layout(height=700)

        st.plotly_chart(heat_fig, use_container_width=True)

    else:
        st.warning("상관관계를 보려면 최소 2개 이상의 기업을 선택하세요.")


# ------------------------------------------------------------
# 다운로드
# ------------------------------------------------------------
st.divider()
st.subheader("데이터 다운로드")

csv = data.to_csv(index=False).encode("utf-8-sig")

st.download_button(
    label="CSV 다운로드",
    data=csv,
    file_name="global_top10_marketcap_history.csv",
    mime="text/csv"
)
