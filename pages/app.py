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

