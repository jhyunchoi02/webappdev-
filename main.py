import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st


# ============================================================
# 기본 설정
# ============================================================
st.set_page_config(
    page_title="부유한 나라일수록 오래 살까?",
    page_icon="🌍",
    layout="wide"
)

GDP_INDICATOR = "NY.GDP.PCAP.CD"      # 1인당 GDP, current US$
LIFE_INDICATOR = "SP.DYN.LE00.IN"     # 기대수명, years
START_YEAR = 2000
CURRENT_YEAR = datetime.date.today().year

# World Bank 기대수명 자료는 최신 연도 결측이 있을 수 있어 2022를 기본값으로 설정
DEFAULT_YEAR = 2022


# ============================================================
# 데이터 불러오기 함수
# ============================================================
@st.cache_data(ttl=60 * 60 * 24)
def get_country_metadata():
    """
    World Bank 국가 정보에서 실제 국가만 가져옵니다.
    """
    url = "https://api.worldbank.org/v2/country"

    params = {
        "format": "json",
        "per_page": 400
    }

    response = requests.get(
        url,
        params=params,
        timeout=(10, 60)
    )

    response.raise_for_status()
    json_data = response.json()

    if len(json_data) < 2 or json_data[1] is None:
        raise ValueError("국가 정보를 불러오지 못했습니다.")

    country_items = json_data[1]
    rows = []

    for item in country_items:
        region_info = item.get("region", {}) or {}
        income_info = item.get("incomeLevel", {}) or {}

        rows.append(
            {
                "country_code": item.get("id"),
                "country_name_meta": item.get("name"),
                "region": region_info.get("value"),
                "income_level": income_info.get("value"),
            }
        )

    df = pd.DataFrame(rows)

    # World, High income, OECD members 등은 region 값이 Aggregates이므로 제외합니다.
    df = df[df["region"].notna()].copy()
    df = df[df["region"] != "Aggregates"].copy()

    return df


@st.cache_data(ttl=60 * 60 * 24)
def get_indicator_data(indicator_code, year):
    """
    선택한 연도의 특정 World Bank 지표를 가져옵니다.
    """
    url = f"https://api.worldbank.org/v2/country/all/indicator/{indicator_code}"

    params = {
        "format": "json",
        "per_page": 1000,
        "date": str(year),
    }

    response = requests.get(
        url,
        params=params,
        timeout=(10, 60)
    )

    response.raise_for_status()
    json_data = response.json()

    if len(json_data) < 2 or json_data[1] is None:
        raise ValueError(f"{year}년 {indicator_code} 데이터를 불러오지 못했습니다.")

    data_items = json_data[1]
    rows = []

    for item in data_items:
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


@st.cache_data(ttl=60 * 60 * 24)
def make_dataset(year):
    """
    1인당 GDP와 기대수명 데이터를 병합해 분석용 데이터프레임을 만듭니다.
    """
    country_df = get_country_metadata()

    gdp_df = get_indicator_data(
        GDP_INDICATOR,
        year
    ).rename(
        columns={"value": "gdp_per_capita"}
    )

    life_df = get_indicator_data(
        LIFE_INDICATOR,
        year
    ).rename(
        columns={"value": "life_expectancy"}
    )

    merged_df = pd.merge(
        gdp_df[
            [
                "country_name",
                "country_code",
                "year",
                "gdp_per_capita"
            ]
        ],
        life_df[
            [
                "country_code",
                "year",
                "life_expectancy"
            ]
        ],
        on=[
            "country_code",
            "year"
        ],
        how="inner"
    )

    merged_df = pd.merge(
        merged_df,
        country_df,
        on="country_code",
        how="inner"
    )

    merged_df["gdp_per_capita"] = pd.to_numeric(
        merged_df["gdp_per_capita"],
        errors="coerce"
    )

    merged_df["life_expectancy"] = pd.to_numeric(
        merged_df["life_expectancy"],
        errors="coerce"
    )

    merged_df = merged_df.dropna(
        subset=[
            "gdp_per_capita",
            "life_expectancy"
        ]
    )

    # 로그 스케일을 사용하기 위해 GDP가 0 이하인 자료는 제거합니다.
    merged_df = merged_df[
        merged_df["gdp_per_capita"] > 0
    ].copy()

    return merged_df


# ============================================================
# 분석 보조 함수
# ============================================================
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


def add_trend_line(fig, df, use_log_scale):
    """
    산점도에 추세선을 추가합니다.
    """
    if len(df) < 2:
        return fig

    x_values = df["gdp_per_capita"].to_numpy(dtype=float)
    y_values = df["life_expectancy"].to_numpy(dtype=float)

    if use_log_scale:
        x_for_fit = np.log10(x_values)
        x_line = np.linspace(
            x_values.min(),
            x_values.max(),
            200
        )
        x_line_for_fit = np.log10(x_line)
    else:
        x_for_fit = x_values
        x_line = np.linspace(
            x_values.min(),
            x_values.max(),
            200
        )
        x_line_for_fit = x_line

    slope, intercept = np.polyfit(
        x_for_fit,
        y_values,
        1
    )

    y_line = slope * x_line_for_fit + intercept

    fig.add_trace(
        go.Scatter(
            x=x_line,
            y=y_line,
            mode="lines",
            name="추세선",
            line=dict(
                color="red",
                width=3
            ),
            hoverinfo="skip"
        )
    )

    return fig


def find_exception_groups(df):
    """
    분위수를 이용해 탐구용 예외 국가를 찾습니다.
    """
    gdp_q1 = df["gdp_per_capita"].quantile(0.25)
    gdp_q3 = df["gdp_per_capita"].quantile(0.75)
    life_q1 = df["life_expectancy"].quantile(0.25)
    life_q3 = df["life_expectancy"].quantile(0.75)

    low_gdp_high_life = df[
        (df["gdp_per_capita"] <= gdp_q1)
        & (df["life_expectancy"] >= life_q3)
    ].copy()

    high_gdp_low_life = df[
        (df["gdp_per_capita"] >= gdp_q3)
        & (df["life_expectancy"] <= life_q1)
    ].copy()

    return low_gdp_high_life, high_gdp_low_life, gdp_q1, gdp_q3


# ============================================================
# 화면 구성
# ============================================================
st.title("🌍 부유한 나라일수록 오래 살까?")
st.caption("World Bank Open Data API를 활용한 산점도와 상관관계 탐구")

st.markdown(
    """
이 앱은 세계 여러 나라의 **1인당 GDP**와 **기대수명** 데이터를 가져와서  
두 변수 사이의 관계를 산점도와 상관계수로 탐구하는 중학교 3학년 통계 수업용 앱입니다.

핵심 질문은 다음과 같습니다.

> **부유한 나라일수록 오래 살까?**
"""
)


# ------------------------------------------------------------
# 사이드바
# ------------------------------------------------------------
st.sidebar.header("⚙️ 분석 조건")

year_options = list(
    range(
        min(CURRENT_YEAR - 2, 2024),
        START_YEAR - 1,
        -1
    )
)

if DEFAULT_YEAR in year_options:
    default_index = year_options.index(DEFAULT_YEAR)
else:
    default_index = 0

selected_year = st.sidebar.selectbox(
    "분석할 연도",
    options=year_options,
    index=default_index
)

scale_option = st.sidebar.radio(
    "x축 스케일",
    options=[
        "로그 스케일",
        "일반 스케일"
    ],
    index=0,
    help="GDP는 나라별 차이가 크므로 로그 스케일이 패턴을 보기 좋습니다."
)

use_log_scale = scale_option == "로그 스케일"


# ------------------------------------------------------------
# 데이터 불러오기
# ------------------------------------------------------------
try:
    with st.spinner(f"{selected_year}년 World Bank 데이터를 불러오는 중입니다..."):
        base_df = make_dataset(selected_year)

except requests.exceptions.ReadTimeout:
    st.error(
        "World Bank API 응답 시간이 길어졌습니다. "
        "잠시 후 다시 실행하거나 다른 연도를 선택해 주세요."
    )
    st.stop()

except requests.exceptions.RequestException as error:
    st.error(
        "World Bank API 요청에 실패했습니다. "
        "인터넷 연결이나 API 상태를 확인해 주세요."
    )
    st.exception(error)
    st.stop()

except Exception as error:
    st.error("데이터 처리 중 오류가 발생했습니다.")
    st.exception(error)
    st.stop()


if base_df.empty:
    st.warning(
        f"{selected_year}년에는 분석 가능한 데이터가 부족합니다. "
        "2022년 또는 2021년을 선택해 보세요."
    )
    st.stop()


# ------------------------------------------------------------
# 필터
# ------------------------------------------------------------
min_gdp = int(base_df["gdp_per_capita"].min())
max_gdp = int(base_df["gdp_per_capita"].max())

min_life = float(
    np.floor(
        base_df["life_expectancy"].min()
    )
)

max_life = float(
    np.ceil(
        base_df["life_expectancy"].max()
    )
)

selected_gdp_range = st.sidebar.slider(
    "1인당 GDP 범위(US$)",
    min_value=min_gdp,
    max_value=max_gdp,
    value=(
        min_gdp,
        max_gdp
    ),
    step=100
)

selected_min_life = st.sidebar.slider(
    "최소 기대수명(년)",
    min_value=min_life,
    max_value=max_life,
    value=min_life,
    step=1.0
)

region_options = [
    "전체"
] + sorted(
    base_df["region"].dropna().unique().tolist()
)

selected_region = st.sidebar.selectbox(
    "지역",
    region_options
)

filtered_df = base_df[
    (base_df["gdp_per_capita"] >= selected_gdp_range[0])
    & (base_df["gdp_per_capita"] <= selected_gdp_range[1])
    & (base_df["life_expectancy"] >= selected_min_life)
].copy()

if selected_region != "전체":
    filtered_df = filtered_df[
        filtered_df["region"] == selected_region
    ].copy()

if filtered_df.empty:
    st.warning("선택한 조건에 해당하는 국가가 없습니다. 필터 범위를 넓혀 주세요.")
    st.stop()


# ------------------------------------------------------------
# 상관계수와 요약 지표
# ------------------------------------------------------------
if len(filtered_df) >= 2:
    pearson_r = filtered_df["gdp_per_capita"].corr(
        filtered_df["life_expectancy"]
    )
else:
    pearson_r = np.nan

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

st.info(
    interpret_correlation(pearson_r)
)


# ------------------------------------------------------------
# 산점도
# ------------------------------------------------------------
st.subheader("📈 산점도: 1인당 GDP와 기대수명")

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
    title="각 점은 하나의 국가를 의미합니다."
)

fig = add_trend_line(
    fig,
    filtered_df,
    use_log_scale
)

fig.update_layout(
    height=650,
    legend_title_text="지역",
    margin=dict(
        l=20,
        r=20,
        t=60,
        b=20
    )
)

if use_log_scale:
    fig.update_xaxes(
        type="log"
    )

st.plotly_chart(
    fig,
    use_container_width=True
)


# ------------------------------------------------------------
# 탐구 질문에 답하는 과정
# ------------------------------------------------------------
st.subheader("🧭 탐구 질문에 답하는 과정")

st.markdown(
    """
### 1단계. 산점도의 전체 방향 보기
점들이 대체로 **오른쪽 위 방향**으로 퍼져 있다면,  
1인당 GDP가 높을수록 기대수명도 높아지는 경향이 있다고 볼 수 있습니다.

### 2단계. 상관계수 r 확인하기
상관계수는 두 변수의 직선 관계가 얼마나 강한지 나타냅니다.  
이 앱에서는 상관계수 r을 자동으로 계산하고, 위쪽에 해석 문장을 함께 보여줍니다.

### 3단계. 예외 국가 찾기
전체 경향과 다르게 보이는 국가를 찾는 것이 중요합니다.  
예외는 “모든 부유한 나라가 반드시 오래 산다”는 식의 성급한 결론을 조심하게 해 줍니다.

### 4단계. 인과관계 단정하지 않기
상관관계가 있다는 것은 두 변수가 함께 움직이는 경향이 있다는 뜻입니다.  
하지만 그것만으로 한 변수가 다른 변수의 원인이라고 말할 수는 없습니다.
"""
)


# ------------------------------------------------------------
# 데이터 기반 힌트
# ------------------------------------------------------------
st.subheader("💡 데이터가 주는 힌트")

low_gdp_high_life, high_gdp_low_life, gdp_q1, gdp_q3 = find_exception_groups(
    filtered_df
)

high_gdp_group = filtered_df[
    filtered_df["gdp_per_capita"] >= gdp_q3
]

low_gdp_group = filtered_df[
    filtered_df["gdp_per_capita"] <= gdp_q1
]

high_gdp_life_mean = high_gdp_group["life_expectancy"].mean()
low_gdp_life_mean = low_gdp_group["life_expectancy"].mean()

hint_col1, hint_col2 = st.columns(2)

hint_col1.metric(
    "GDP 상위 25% 국가의 평균 기대수명",
    f"{high_gdp_life_mean:.1f}년"
)

hint_col2.metric(
    "GDP 하위 25% 국가의 평균 기대수명",
    f"{low_gdp_life_mean:.1f}년"
)

if high_gdp_life_mean > low_gdp_life_mean:
    st.success(
        "현재 선택한 데이터에서는 GDP 상위 25% 국가의 평균 기대수명이 "
        "GDP 하위 25% 국가보다 높습니다."
    )
else:
    st.warning(
        "현재 선택한 데이터에서는 GDP 상위 25% 국가의 평균 기대수명이 "
        "더 높게 나타나지 않았습니다. 연도나 지역을 바꿔 살펴보세요."
    )


# ------------------------------------------------------------
# 예외 국가 자동 찾기
# ------------------------------------------------------------
st.subheader("🔍 예외적인 국가 찾아보기")

left, right = st.columns(2)

with left:
    st.markdown("### GDP는 낮지만 기대수명이 높은 나라")

    if low_gdp_high_life.empty:
        st.write("현재 조건에서는 뚜렷한 예외 국가가 보이지 않습니다.")
    else:
        table1 = low_gdp_high_life[
            [
                "country_name",
                "gdp_per_capita",
                "life_expectancy",
                "region"
            ]
        ].sort_values(
            "life_expectancy",
            ascending=False
        ).head(10)

        table1 = table1.rename(
            columns={
                "country_name": "국가명",
                "gdp_per_capita": "1인당 GDP",
                "life_expectancy": "기대수명",
                "region": "지역",
            }
        )

        st.dataframe(
            table1,
            use_container_width=True,
            hide_index=True,
            column_config={
                "1인당 GDP": st.column_config.NumberColumn(
                    format="$%,.0f"
                ),
                "기대수명": st.column_config.NumberColumn(
                    format="%.1f년"
                ),
            }
        )

with right:
    st.markdown("### GDP는 높지만 기대수명이 낮은 나라")

    if high_gdp_low_life.empty:
        st.write("현재 조건에서는 뚜렷한 예외 국가가 보이지 않습니다.")
    else:
        table2 = high_gdp_low_life[
            [
                "country_name",
                "gdp_per_capita",
                "life_expectancy",
                "region"
            ]
        ].sort_values(
            "life_expectancy",
            ascending=True
        ).head(10)

        table2 = table2.rename(
            columns={
                "country_name": "국가명",
                "gdp_per_capita": "1인당 GDP",
                "life_expectancy": "기대수명",
                "region": "지역",
            }
        )

        st.dataframe(
            table2,
            use_container_width=True,
            hide_index=True,
            column_config={
                "1인당 GDP": st.column_config.NumberColumn(
                    format="$%,.0f"
                ),
                "기대수명": st.column_config.NumberColumn(
                    format="%.1f년"
                ),
            }
        )


# ------------------------------------------------------------
# 학생 활동
# ------------------------------------------------------------
st.subheader("✏️ 학생 활동")

st.markdown(
    """
아래 문장을 완성하며 자신의 결론을 정리해 봅시다.

> 상관계수 r은 약 ___이다.  
> 산점도를 보면 1인당 GDP가 높을수록 기대수명이 __________ 경향이 있다.  
> 하지만 __________ 때문에 이것만으로 인과관계를 단정할 수는 없다.
"""
)

student_answer = st.text_area(
    "나의 결론 쓰기",
    placeholder=(
        "예: 상관계수 r이 양수이고 산점도가 오른쪽 위 방향으로 퍼져 있으므로, "
        "1인당 GDP와 기대수명 사이에는 양의 상관관계가 있다. "
        "하지만 예외 국가가 있고 다른 요인도 영향을 줄 수 있으므로 "
        "인과관계를 단정할 수는 없다."
    )
)


# ------------------------------------------------------------
# 더 공부해볼 거리
# ------------------------------------------------------------
st.subheader("📚 더 공부해볼 거리")

with st.expander("1. 로그 스케일은 왜 필요할까?"):
    st.write(
        "GDP는 나라별 차이가 매우 크기 때문에 일반 스케일에서는 "
        "점들이 왼쪽에 몰려 보일 수 있습니다. "
        "로그 스케일은 큰 차이를 한 그래프에서 비교하기 쉽게 해 줍니다."
    )

with st.expander("2. 이상치는 상관계수에 어떤 영향을 줄까?"):
    st.write(
        "전체 경향에서 많이 벗어난 국가는 상관계수 값을 크게 바꿀 수 있습니다. "
        "이상치를 무조건 제거하기보다는 왜 그런 값이 나왔는지 먼저 해석해야 합니다."
    )

with st.expander("3. 지역별로 상관관계가 같을까?"):
    st.write(
        "세계 전체에서는 양의 상관관계가 보여도, 특정 지역만 보면 "
        "관계가 약해지거나 다르게 나타날 수 있습니다. "
        "지역 필터를 바꿔 비교해 보세요."
    )

with st.expander("4. 기대수명에 영향을 줄 수 있는 다른 요인은 무엇일까?"):
    st.write(
        "의료, 교육, 식수, 영양, 전쟁, 감염병, 환경, 복지 제도 등 "
        "다양한 요인이 기대수명에 영향을 줄 수 있습니다."
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
        "life_expectancy"
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
# 최종 탐구 질문
# ------------------------------------------------------------
st.subheader("🔎 최종 탐구 질문")

st.markdown(
    """
1. **1인당 GDP가 높은 나라들은 대체로 기대수명이 높은가?**

2. **1인당 GDP가 낮지만 기대수명이 비교적 높은 나라는 있는가?**

3. **상관관계가 있다고 해서 ‘부유하면 반드시 오래 산다’고 말할 수 있을까?**
"""
)

st.success(
    "정리: 산점도와 상관계수는 두 변수 사이의 관계를 이해하는 데 도움을 주지만, "
    "상관관계가 곧 인과관계를 의미하는 것은 아닙니다."
)
