import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st


# ------------------------------------------------------------
# Streamlit 기본 설정
# ------------------------------------------------------------
st.set_page_config(
    page_title="부유한 나라일수록 오래 살까?",
    page_icon="🌍",
    layout="wide"
)


# ------------------------------------------------------------
# World Bank 지표 코드
# ------------------------------------------------------------
GDP_INDICATOR = "NY.GDP.PCAP.CD"       # 1인당 GDP, current US$
LIFE_INDICATOR = "SP.DYN.LE00.IN"      # 기대수명, years

START_YEAR = 2000
CURRENT_YEAR = datetime.date.today().year

# World Bank 자료는 보통 1~2년 늦게 제공되므로 기본 연도는 현재연도 - 2로 설정
DEFAULT_YEAR = CURRENT_YEAR - 2


# ------------------------------------------------------------
# World Bank 국가 메타데이터 불러오기
# ------------------------------------------------------------
@st.cache_data(ttl=60 * 60 * 24)
def load_country_metadata():
    """
    World Bank 국가 메타데이터를 불러옵니다.
    World, High income, OECD members 같은 집계 데이터는 제외하고,
    실제 국가만 남기기 위해 사용합니다.
    """
    url = "https://api.worldbank.org/v2/country"

    params = {
        "format": "json",
        "per_page": 400
    }

    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()

    raw = response.json()

    if len(raw) < 2 or raw[1] is None:
        raise ValueError("국가 메타데이터를 불러오지 못했습니다.")

    rows = []

    for item in raw[1]:
        region = item.get("region", {}) or {}
        income = item.get("incomeLevel", {}) or {}

        rows.append(
            {
                "country_code": item.get("id"),
                "country_name_meta": item.get("name"),
                "region": region.get("value"),
                "income_level": income.get("value"),
            }
        )

    meta_df = pd.DataFrame(rows)

    # region 값이 Aggregates인 자료는 실제 국가가 아니라 집계 자료입니다.
    meta_df = meta_df[meta_df["region"].notna()]
    meta_df = meta_df[meta_df["region"] != "Aggregates"].copy()

    return meta_df


# ------------------------------------------------------------
# World Bank 지표 데이터 불러오기
# ------------------------------------------------------------
@st.cache_data(ttl=60 * 60 * 24)
def load_indicator_for_year(indicator_code, year):
    """
    World Bank API에서 특정 연도, 특정 지표 데이터만 불러옵니다.
    전체 연도를 한 번에 불러오면 Streamlit Cloud에서 시간 초과가 날 수 있어
    선택한 연도 1개만 불러오도록 설계했습니다.
    """
    url = f"https://api.worldbank.org/v2/country/all/indicator/{indicator_code}"

    params = {
        "format": "json",
        "per_page": 500,
        "date": str(year),
    }

    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()

    raw = response.json()

    if len(raw) < 2 or raw[1] is None:
        raise ValueError(f"{year}년 {indicator_code} 데이터를 불러오지 못했습니다.")

    rows = []

    for item in raw[1]:
        country_info = item.get("country", {}) or {}

        rows.append(
            {
                "country_name": country_info.get("value"),
                "country_code": item.get("countryiso3code"),
                "year": int(item.get("date")),
                "value": item.get("value"),
            }
        )

    return pd.DataFrame(rows)


# ------------------------------------------------------------
# GDP와 기대수명 데이터 병합
# ------------------------------------------------------------
@st.cache_data(ttl=60 * 60 * 24)
def make_merged_dataset(selected_year):
    """
    선택한 연도의 1인당 GDP와 기대수명 데이터를 병합하여
    분석용 데이터프레임을 만듭니다.
    """
    country_meta = load_country_metadata()

    # 선택한 연도의 1인당 GDP 데이터
    gdp_df = load_indicator_for_year(
        GDP_INDICATOR,
        selected_year
    ).rename(
        columns={"value": "gdp_per_capita"}
    )

    # 선택한 연도의 기대수명 데이터
    life_df = load_indicator_for_year(
        LIFE_INDICATOR,
        selected_year
    ).rename(
        columns={"value": "life_expectancy"}
    )

    # 국가 코드와 연도를 기준으로 두 지표를 병합합니다.
    merged_df = pd.merge(
        gdp_df[["country_name", "country_code", "year", "gdp_per_capita"]],
        life_df[["country_code", "year", "life_expectancy"]],
        on=["country_code", "year"],
        how="inner"
    )

    # 실제 국가만 남기고 지역, 소득수준 정보를 추가합니다.
    merged_df = pd.merge(
        merged_df,
        country_meta,
        on="country_code",
        how="inner"
    )

    # 숫자형 변환
    merged_df["gdp_per_capita"] = pd.to_numeric(
        merged_df["gdp_per_capita"],
        errors="coerce"
    )

    merged_df["life_expectancy"] = pd.to_numeric(
        merged_df["life_expectancy"],
        errors="coerce"
    )

    # 결측값 제거
    merged_df = merged_df.dropna(
        subset=["gdp_per_capita", "life_expectancy"]
    )

    # 로그 스케일에서 사용할 수 있도록 GDP가 0 이하인 자료는 제거합니다.
    merged_df = merged_df[merged_df["gdp_per_capita"] > 0].copy()

    return merged_df


# ------------------------------------------------------------
# 상관계수 해석 함수
# ------------------------------------------------------------
def interpret_correlation(r):
    """
    피어슨 상관계수를 학생 눈높이로 해석합니다.
    """
    if pd.isna(r):
        return "데이터가 부족하여 상관계수를 해석하기 어렵습니다."

    if r >= 0.7:
        return "강한 양의 상관관계가 있습니다. 1인당 GDP가 높을수록 기대수명도 높은 경향이 뚜렷합니다."

    if r >= 0.3:
        return "어느 정도 양의 상관관계가 있습니다. 1인당 GDP가 높을수록 기대수명이 높아지는 경향이 보입니다."

    if r > -0.3:
        return "뚜렷한 직선 관계는 약합니다. 두 변수 사이의 관계가 강하다고 보기 어렵습니다."

    if r > -0.7:
        return "어느 정도 음의 상관관계가 있습니다. 한 변수가 커질 때 다른 변수가 작아지는 경향이 보입니다."

    return "강한 음의 상관관계가 있습니다. 한 변수가 커질수록 다른 변수가 작아지는 경향이 뚜렷합니다."


# ------------------------------------------------------------
# 추세선 추가 함수
# ------------------------------------------------------------
def add_regression_line(fig, df, use_log_scale):
    """
    산점도 위에 간단한 1차 추세선을 추가합니다.
    로그 스케일일 때는 log10(GDP)를 기준으로 추세선을 계산합니다.
    """
    if len(df) < 2:
        return fig

    x = df["gdp_per_capita"].to_numpy(dtype=float)
    y = df["life_expectancy"].to_numpy(dtype=float)

    if use_log_scale:
        x_for_fit = np.log10(x)
        x_line = np.linspace(x.min(), x.max(), 200)
        x_line_for_fit = np.log10(x_line)
    else:
        x_for_fit = x
        x_line = np.linspace(x.min(), x.max(), 200)
        x_line_for_fit = x_line

    slope, intercept = np.polyfit(x_for_fit, y, 1)
    y_line = slope * x_line_for_fit + intercept

    fig.add_trace(
        go.Scatter(
            x=x_line,
            y=y_line,
            mode="lines",
            name="추세선",
            line=dict(color="red", width=3),
            hoverinfo="skip"
        )
    )

    return fig


# ------------------------------------------------------------
# 앱 제목 및 안내
# ------------------------------------------------------------
st.title("🌍 부유한 나라일수록 오래 살까?")
st.caption("World Bank 데이터를 활용한 산점도와 상관관계 탐구")

st.markdown(
    """
이 앱은 세계 여러 나라의 **1인당 GDP**와 **기대수명** 데이터를 불러와  
두 변수 사이의 관계를 살펴보는 중학교 3학년 통계 탐구 앱입니다.

학생들은 산점도와 상관계수를 통해 다음 내용을 탐구합니다.

- 1인당 GDP가 높은 나라들은 대체로 기대수명이 높은가?
- 1인당 GDP가 낮지만 기대수명이 비교적 높은 나라는 있는가?
- 상관관계가 있다고 해서 인과관계라고 말할 수 있는가?
"""
)


# ------------------------------------------------------------
# 사이드바: 분석 조건 선택
# ------------------------------------------------------------
st.sidebar.header("⚙️ 분석 조건 선택")

year_options = list(range(CURRENT_YEAR - 2, START_YEAR - 1, -1))

if DEFAULT_YEAR in year_options:
    default_index = year_options.index(DEFAULT_YEAR)
else:
    default_index = 0

selected_year = st.sidebar.selectbox(
    "분석할 연도 선택",
    options=year_options,
    index=default_index,
    help="World Bank 최신 자료는 보통 1~2년 늦게 제공되므로 최근에서 2년 전을 기본값으로 설정했습니다."
)

scale_option = st.sidebar.radio(
    "x축 스케일 선택",
    options=["로그 스케일", "일반 스케일"],
    index=0,
    help="GDP는 국가별 차이가 매우 커서 로그 스케일이 패턴을 보기 좋습니다."
)

use_log_scale = scale_option == "로그 스케일"


# ------------------------------------------------------------
# 데이터 불러오기
# ------------------------------------------------------------
try:
    with st.spinner(f"{selected_year}년 World Bank 데이터를 불러오는 중입니다..."):
        base_df = make_merged_dataset(selected_year)

except requests.exceptions.ReadTimeout:
    st.error(
        "World Bank API 응답 시간이 길어져 데이터를 불러오지 못했습니다. "
        "잠시 후 다시 실행하거나 다른 연도를 선택해 주세요."
    )
    st.stop()

except requests.exceptions.RequestException as error:
    st.error("World Bank API 요청에 실패했습니다. 인터넷 연결 또는 API 상태를 확인해 주세요.")
    st.exception(error)
    st.stop()

except Exception as error:
    st.error("데이터를 처리하는 중 오류가 발생했습니다.")
    st.exception(error)
    st.stop()


if base_df.empty:
    st.warning(
        f"{selected_year}년에는 분석 가능한 데이터가 부족합니다. "
        "다른 연도를 선택해 주세요."
    )
    st.stop()


# ------------------------------------------------------------
# 필터 설정
# ------------------------------------------------------------
min_gdp = float(base_df["gdp_per_capita"].min())
max_gdp = float(base_df["gdp_per_capita"].max())

min_life = float(base_df["life_expectancy"].min())
max_life = float(base_df["life_expectancy"].max())

selected_gdp_range = st.sidebar.slider(
    "1인당 GDP 범위(US$)",
    min_value=int(min_gdp),
    max_value=int(max_gdp),
    value=(int(min_gdp), int(max_gdp)),
    step=100
)

selected_min_life = st.sidebar.slider(
    "최소 기대수명(년)",
    min_value=float(np.floor(min_life)),
    max_value=float(np.ceil(max_life)),
    value=float(np.floor(min_life)),
    step=1.0
)

region_options = ["전체"] + sorted(
    base_df["region"].dropna().unique().tolist()
)

selected_region = st.sidebar.selectbox(
    "지역 선택",
    region_options
)


# ------------------------------------------------------------
# 필터 적용
# ------------------------------------------------------------
filtered_df = base_df[
    (base_df["gdp_per_capita"] >= selected_gdp_range[0])
    & (base_df["gdp_per_capita"] <= selected_gdp_range[1])
    & (base_df["life_expectancy"] >= selected_min_life)
].copy()

if selected_region != "전체":
    filtered_df = filtered_df[filtered_df["region"] == selected_region].copy()

if filtered_df.empty:
    st.warning("선택한 조건에 해당하는 국가가 없습니다. 필터 범위를 넓혀 주세요.")
    st.stop()


# ------------------------------------------------------------
# 상관계수 계산
# ------------------------------------------------------------
if len(filtered_df) >= 2:
    pearson_r = filtered_df["gdp_per_capita"].corr(
        filtered_df["life_expectancy"]
    )
else:
    pearson_r = np.nan


# ------------------------------------------------------------
# 주요 지표 카드
# ------------------------------------------------------------
st.subheader(f"📌 {selected_year}년 분석 결과")

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "분석 국가 수",
    f"{len(filtered_df):,}개"
)

col2.metric(
    "평균 1인당 GDP",
    f"${filtered_df['gdp_per_capita'].mean():,.0f}"
)

col3.metric(
    "평균 기대수명",
    f"{filtered_df['life_expectancy'].mean():.1f}년"
)

col4.metric(
    "피어슨 상관계수 r",
    "-" if pd.isna(pearson_r) else f"{pearson_r:.3f}"
)

st.info(interpret_correlation(pearson_r))


# ------------------------------------------------------------
# 산점도
# ------------------------------------------------------------
st.subheader("📈 1인당 GDP와 기대수명의 산점도")

fig = px.scatter(
    filtered_df,
    x="gdp_per_capita",
    y="life_expectancy",
    color="region",
    hover_name="country_name",
    hover_data={
        "gdp_per_capita": ":,.0f",
        "life_expectancy": ":.1f",
        "region": True,
        "income_level": True,
    },
    labels={
        "gdp_per_capita": "1인당 GDP(현재 US$)",
        "life_expectancy": "기대수명(년)",
        "region": "지역",
        "income_level": "소득 수준",
    },
    title="한 점은 하나의 국가를 의미합니다."
)

fig = add_regression_line(
    fig,
    filtered_df,
    use_log_scale
)

fig.update_layout(
    height=650,
    legend_title_text="지역",
    margin=dict(l=20, r=20, t=60, b=20)
)

if use_log_scale:
    fig.update_xaxes(type="log")

st.plotly_chart(
    fig,
    use_container_width=True
)

if use_log_scale:
    st.caption("참고: 현재 그래프는 로그 스케일입니다. GDP 차이가 큰 나라들을 한 화면에서 비교하기 좋습니다.")
else:
    st.caption("참고: 현재 그래프는 일반 스케일입니다. GDP가 매우 큰 국가 때문에 왼쪽에 점들이 몰려 보일 수 있습니다.")


# ------------------------------------------------------------
# 수학 개념 설명
# ------------------------------------------------------------
with st.expander("📚 수학 개념 정리 보기"):
    st.markdown(
        """
### 산점도
두 수치 자료의 관계를 점으로 나타낸 그래프입니다.  
이 앱에서 **한 점은 하나의 국가**를 의미합니다.

### 양의 상관관계
x값이 커질수록 y값도 커지는 경향이 있을 때를 말합니다.

### 음의 상관관계
x값이 커질수록 y값은 작아지는 경향이 있을 때를 말합니다.

### 상관계수
두 변수 사이의 관계가 얼마나 강한지 **-1에서 1 사이의 수**로 나타낸 값입니다.

- 1에 가까움: 강한 양의 상관관계
- -1에 가까움: 강한 음의 상관관계
- 0에 가까움: 뚜렷한 직선 관계가 약함

### 상관관계와 인과관계
상관관계는 두 변수가 함께 움직이는 경향입니다.  
인과관계는 한 변수가 다른 변수의 원인이 되는 관계입니다.

따라서 산점도와 상관계수만으로  
“부유하기 때문에 반드시 오래 산다”라고 단정하면 안 됩니다.
"""
    )


# ------------------------------------------------------------
# 데이터 표
# ------------------------------------------------------------
st.subheader("🧾 필터링된 데이터 표")

display_df = filtered_df[
    [
        "country_name",
        "country_code",
        "year",
        "region",
        "income_level",
        "gdp_per_capita",
        "life_expectancy",
    ]
].rename(
    columns={
        "country_name": "국가명",
        "country_code": "국가 코드",
        "year": "연도",
        "region": "지역",
        "income_level": "소득 수준",
        "gdp_per_capita": "1인당 GDP(US$)",
        "life_expectancy": "기대수명(년)",
    }
)

display_df = display_df.sort_values(
    "1인당 GDP(US$)",
    ascending=False
)

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "1인당 GDP(US$)": st.column_config.NumberColumn(
            format="$%,.0f"
        ),
        "기대수명(년)": st.column_config.NumberColumn(
            format="%.1f"
        ),
    }
)


# ------------------------------------------------------------
# 탐구 질문
# ------------------------------------------------------------
st.subheader("🔎 탐구 질문")

st.markdown(
    """
1. **1인당 GDP가 높은 나라들은 대체로 기대수명이 높은가?**

2. **1인당 GDP가 낮지만 기대수명이 비교적 높은 나라는 있는가?**

3. **상관관계가 있다고 해서 ‘부유하면 반드시 오래 산다’고 말할 수 있을까?**
"""
)

st.success(
    "수업 정리: 산점도와 상관계수는 두 변수 사이의 관계를 이해하는 데 도움을 주지만, "
    "상관관계가 곧 인과관계를 의미하는 것은 아닙니다."
)
