# -*- coding: utf-8 -*-
"""
어제자 KOBIS(영화진흥위원회) 일별 박스오피스를 보여주는 스트림릿 앱.

- 인증키는 코드에 쓰지 않고 st.secrets["KOBIS_KEY"]에서 불러옵니다.
  -> 로컬에서는 .streamlit/secrets.toml 에 KOBIS_KEY = "발급받은키" 형태로 넣고,
     스트림릿 클라우드에서는 앱 설정(Settings) > Secrets 에 똑같이 넣어주면 됩니다.
- '어제' 날짜는 한국 시간(KST) 기준으로 서버 위치와 상관없이 자동 계산합니다.
- 같은 날짜 조회 결과는 1시간 동안 캐시해서 API를 반복 호출하지 않습니다.
"""

import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ------------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------------
st.set_page_config(page_title="어제의 박스오피스", page_icon="🎬", layout="wide")

KOBIS_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

# 표/그래프에서 실제로 숫자로 다뤄야 하는 컬럼들 (API에서는 전부 문자열로 옴)
NUMERIC_COLS = ["rank", "audiCnt", "audiAcc", "scrnCnt"]


def get_yesterday_kst() -> str:
    """서버 시간대와 상관없이, 한국 시간(KST) 기준 '어제' 날짜를 yyyymmdd 문자열로 돌려준다.
    오늘 날짜 데이터는 KOBIS 집계가 아직 끝나지 않아서 조회 대상에서 제외한다."""
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    yesterday = now_kst - timedelta(days=1)
    return yesterday.strftime("%Y%m%d")


@st.cache_data(ttl=3600)  # 같은 날짜(target_dt)로 다시 부르면 1시간 동안은 캐시된 결과를 재사용
def fetch_box_office(target_dt: str, api_key: str) -> dict:
    """KOBIS API를 호출해서 원본 JSON(dict)을 그대로 돌려준다.
    네트워크 오류가 나면 예외를 그대로 위로 던지고, 호출하는 쪽에서 처리한다."""
    params = {"key": api_key, "targetDt": target_dt}
    response = requests.get(KOBIS_URL, params=params, timeout=10)
    response.raise_for_status()  # 상태코드가 200이 아니면 여기서 예외 발생
    return response.json()


def to_dataframe(daily_list: list) -> pd.DataFrame:
    """API가 준 영화 목록(list[dict])을 pandas DataFrame으로 바꾸고,
    문자열로 온 숫자 컬럼들을 실제 숫자(int)로 변환한다."""
    df = pd.DataFrame(daily_list)
    for col in NUMERIC_COLS:
        # errors="coerce": 혹시 이상한 값이 섞여 있어도 앱이 죽지 않고 NaN 처리
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("rank").reset_index(drop=True)
    return df


def show_guide_message(reason: str):
    """빈 화면 대신, 무엇을 확인해야 하는지 한국어로 친절하게 안내한다."""
    st.error(reason)
    st.markdown(
        """
**아래 항목을 확인해 보세요.**

1. 스트림릿 클라우드 앱 설정(Settings) → **Secrets** 에 `KOBIS_KEY` 가 정확히 등록되어 있는지
2. KOBIS(영화진흥위원회) 사이트에서 발급받은 인증키가 맞는지, 만료되지는 않았는지
3. 조회하려는 날짜에 박스오피스 데이터가 실제로 존재하는지 (너무 이른 새벽에는 전날 집계가 늦어질 수 있음)
4. 인터넷 연결 상태 및 KOBIS 서버 상태
        """
    )


# ------------------------------------------------------------------
# 화면 구성 시작
# ------------------------------------------------------------------
st.title("🎬 어제의 박스오피스")

target_dt = get_yesterday_kst()
display_date = f"{target_dt[:4]}.{target_dt[4:6]}.{target_dt[6:]}"
st.caption(f"조회 기준일(한국 시간 기준 어제): {display_date}")

# secrets에서 인증키 불러오기 (없으면 안내 메시지 후 앱 중단)
api_key = st.secrets.get("KOBIS_KEY")
if not api_key:
    show_guide_message("인증키(KOBIS_KEY)를 찾을 수 없습니다. Secrets 설정을 확인해 주세요.")
    st.stop()

# 1) API 호출 (실패 시 안내 후 중단)
try:
    raw_data = fetch_box_office(target_dt, api_key)
except requests.exceptions.RequestException:
    show_guide_message("KOBIS 서버에 접속하지 못했습니다. 잠시 후 다시 시도해 주세요.")
    st.stop()

# 2) 오류 상자(faultInfo) 확인
if "faultInfo" in raw_data:
    fault_msg = raw_data["faultInfo"].get("message", "알 수 없는 오류")
    show_guide_message(f"KOBIS API가 오류를 반환했습니다: {fault_msg}")
    st.stop()

# 3) boxOfficeResult / dailyBoxOfficeList 구조 확인
box_office_result = raw_data.get("boxOfficeResult", {})
daily_list = box_office_result.get("dailyBoxOfficeList", [])

if not daily_list:
    show_guide_message("영화 목록이 비어 있습니다. 조회 날짜에 데이터가 아직 없을 수 있습니다.")
    st.stop()

# 4) 데이터프레임 변환 (문자열 숫자 -> 실제 숫자)
df = to_dataframe(daily_list)

# ------------------------------------------------------------------
# 1위 영화 - 지표 카드 3장
# ------------------------------------------------------------------
top1 = df.iloc[0]
st.subheader(f"🥇 1위: {top1['movieNm']}")

col1, col2, col3 = st.columns(3)
col1.metric("어제 관객수", f"{top1['audiCnt']:,}명")
col2.metric("누적 관객수", f"{top1['audiAcc']:,}명")
col3.metric("스크린수", f"{top1['scrnCnt']:,}개")

st.divider()

# ------------------------------------------------------------------
# 관객수 상위 5편 - 막대그래프
# ------------------------------------------------------------------
st.subheader("📊 관객수 상위 5편")
top5 = df.nlargest(5, "audiCnt").set_index("movieNm")
st.bar_chart(top5["audiCnt"])

st.divider()

# ------------------------------------------------------------------
# 전체 표
# ------------------------------------------------------------------
st.subheader("📋 전체 박스오피스")

table_df = df[["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
table_df.columns = ["순위", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]

st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "관객수": st.column_config.NumberColumn(format="%d"),
        "누적관객": st.column_config.NumberColumn(format="%d"),
        "스크린수": st.column_config.NumberColumn(format="%d"),
    },
)
