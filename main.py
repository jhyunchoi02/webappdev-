import streamlit as st
import random
import pandas as pd

# 🎨 페이지 설정
st.set_page_config(
    page_title="🎲 확률 카지노 연구소",
    page_icon="🎰",
    layout="wide"
)

# 🌈 CSS 꾸미기
st.markdown("""
<style>

.main {
    background-color: #0f172a;
}

.title {
    text-align: center;
    font-size: 55px;
    font-weight: bold;
    color: #ffd700;
}

.sub {
    text-align: center;
    font-size: 23px;
    color: white;
}

.coin-box {
    background: linear-gradient(135deg, #f7971e, #ffd200);
    padding: 20px;
    border-radius: 20px;
    text-align: center;
    font-size: 30px;
    font-weight: bold;
    color: black;
    margin-bottom: 20px;
}

.game-card {
    background: linear-gradient(135deg, #667eea, #764ba2);
    padding: 20px;
    border-radius: 20px;
    color: white;
    margin-top: 20px;
}

.result-win {
    background-color: #22c55e;
    padding: 15px;
    border-radius: 15px;
    color: white;
    font-size: 25px;
    text-align: center;
}

.result-lose {
    background-color: #ef4444;
    padding: 15px;
    border-radius: 15px;
    color: white;
    font-size: 25px;
    text-align: center;
}

</style>
""", unsafe_allow_html=True)

# 🎰 제목
st.markdown(
    "<div class='title'>🎲 확률 카지노 연구소 🎰</div>",
    unsafe_allow_html=True
)

st.markdown(
    "<div class='sub'>💰 확률을 계산하며 최고의 전략가가 되어보세요! 📊</div>",
    unsafe_allow_html=True
)

st.write("")

# 💰 코인 초기화
if "coins" not in st.session_state:
    st.session_state.coins = 10000

if "history" not in st.session_state:
    st.session_state.history = []

# 💵 현재 코인
st.markdown(
    f"<div class='coin-box'>💵 현재 코인: {st.session_state.coins} 코인</div>",
    unsafe_allow_html=True
)

# 🎮 게임 선택
game = st.selectbox(
    "🎯 게임을 선택하세요!",
    ["🎲 주사위 게임", "🎡 룰렛 게임", "🃏 카드 게임"]
)

# 💸 배팅 금액
bet = st.number_input(
    "💸 배팅 금액 입력",
    min_value=100,
    max_value=st.session_state.coins,
    value=500,
    step=100
)

# 🎲 주사위 게임
if game == "🎲 주사위 게임":

    st.markdown("""
    <div class='game-card'>
    🎲 주사위에서 6이 나오면 성공!<br>
    ✅ 성공 확률: 1/6<br>
    ✅ 성공 시: 3배 지급
    </div>
    """, unsafe_allow_html=True)

    if st.button("🎲 주사위 굴리기!"):

        dice = random.randint(1, 6)

        st.write(f"🎲 나온 숫자: {dice}")

        if dice == 6:
            reward = bet * 3
            st.session_state.coins += reward

            st.markdown(
                f"<div class='result-win'>🎉 성공! +{reward} 코인 획득!</div>",
                unsafe_allow_html=True
            )

            result = "성공"

        else:
            st.session_state.coins -= bet

            st.markdown(
                f"<div class='result-lose'>😭 실패! -{bet} 코인 잃음!</div>",
                unsafe_allow_html=True
            )

            result = "실패"

        st.session_state.history.append({
            "게임": "주사위",
            "결과": result,
            "현재코인": st.session_state.coins
        })

# 🎡 룰렛 게임
elif game == "🎡 룰렛 게임":

    st.markdown("""
    <div class='game-card'>
    🎡 룰렛 색상 맞추기!<br><br>

    🟢 초록: 10% → 10배<br>
    🔵 파랑: 30% → 3배<br>
    🔴 빨강: 60% → 1.5배
    </div>
    """, unsafe_allow_html=True)

    color = st.radio(
        "🎨 색상을 선택하세요!",
        ["🟢 초록", "🔵 파랑", "🔴 빨강"]
    )

    if st.button("🎡 룰렛 돌리기!"):

        rand = random.random()

        if rand < 0.1:
            result_color = "🟢 초록"
            multiplier = 10

        elif rand < 0.4:
            result_color = "🔵 파랑"
            multiplier = 3

        else:
            result_color = "🔴 빨강"
            multiplier = 1.5

        st.write(f"🎯 결과 색상: {result_color}")

        if color == result_color:

            reward = int(bet * multiplier)

            st.session_state.coins += reward

            st.markdown(
                f"<div class='result-win'>🎉 성공! +{reward} 코인!</div>",
                unsafe_allow_html=True
            )

            result = "성공"

        else:
            st.session_state.coins -= bet

            st.markdown(
                f"<div class='result-lose'>😭 실패! -{bet} 코인!</div>",
                unsafe_allow_html=True
            )

            result = "실패"

        st.session_state.history.append({
            "게임": "룰렛",
            "결과": result,
            "현재코인": st.session_state.coins
        })

# 🃏 카드 게임
elif game == "🃏 카드 게임":

    st.markdown("""
    <div class='game-card'>
    🃏 빨간 카드가 나오면 성공!<br>
    ❤️ 성공 확률: 50%<br>
    ✅ 성공 시: 2배 지급
    </div>
    """, unsafe_allow_html=True)

    if st.button("🃏 카드 뽑기!"):

        card = random.choice(["❤️ 빨강", "🖤 검정"])

        st.write(f"🃏 뽑은 카드: {card}")

        if "빨강" in card:

            reward = bet * 2

            st.session_state.coins += reward

            st.markdown(
                f"<div class='result-win'>🎉 성공! +{reward} 코인!</div>",
                unsafe_allow_html=True
            )

            result = "성공"

        else:
            st.session_state.coins -= bet

            st.markdown(
                f"<div class='result-lose'>😭 실패! -{bet} 코인!</div>",
                unsafe_allow_html=True
            )

            result = "실패"

        st.session_state.history.append({
            "게임": "카드",
            "결과": result,
            "현재코인": st.session_state.coins
        })

# 📊 통계
st.write("")
st.write("")

st.subheader("📊 나의 게임 통계")

if len(st.session_state.history) > 0:

    df = pd.DataFrame(st.session_state.history)

    st.dataframe(df, use_container_width=True)

    success_count = len(df[df["결과"] == "성공"])
    total_count = len(df)

    success_rate = round((success_count / total_count) * 100, 2)

    st.metric("🎯 승률", f"{success_rate}%")

    st.line_chart(df["현재코인"])

else:
    st.info("🎮 아직 게임 기록이 없습니다!")

# 🚨 게임 종료
if st.session_state.coins <= 0:

    st.error("💀 코인을 모두 잃었습니다!")

    if st.button("🔄 다시 시작하기"):

        st.session_state.coins = 10000
        st.session_state.history = []

# 🌈 하단 문구
st.write("")
st.markdown("""
<hr>
<h3 style='text-align:center; color:gray;'>
🧠 확률은 운이 아니라 수학입니다! 🎲📈
</h3>
""", unsafe_allow_html=True)
