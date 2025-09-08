# app.py
import time
import random
from datetime import datetime

import streamlit as st
import pandas as pd

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import APIError

# ------------------- CONFIG -------------------
GOOGLE_SHEET_NAME = "UrbanSoundscapeData"   # 你的 Google 表格名
WORKSHEET_INDEX = 0                         # 第几个工作表（0 表示第一个）

# 刺激库
STIMULI = [
    {"id": "S01", "image": "i_qeop_3.jpg", "audio": "a_3_garden.wav"},
    {"id": "S02", "image": "i_qeop_2.jpg", "audio": "a_2_spring music.wav"},
    {"id": "S03", "image": "i_qeop_1.jpg", "audio": "a_1_east village.wav"},
]

TRIALS_PER_PARTICIPANT = min(3, len(STIMULI))  # 每位受试的试次数
MIN_LISTEN_SECONDS = 3                         # 最少收听时长门槛
# ----------------------------------------------

st.set_page_config(page_title="Urban Acoustic Comfort Test", page_icon="🎧", layout="centered")

# -------------- Google Sheets 客户端 --------------
@st.cache_resource(show_spinner=False)
def get_gs_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        if "gcp_service_account" in st.secrets:
            info = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Google Sheets auth failed: {e}")
        st.stop()

@st.cache_resource(show_spinner=False)
def open_worksheet():
    client = get_gs_client()
    sh = client.open(GOOGLE_SHEET_NAME)
    ws = sh.get_worksheet(WORKSHEET_INDEX)
    return ws

def append_row_with_retry(ws, row_values, max_retries=1):
    for i in range(max_retries):
        try:
            ws.append_row(row_values)
            return True
        except APIError:
            wait = 2 ** i
            time.sleep(wait)
        except Exception as e:
            st.warning(f"Append failed (attempt {i+1}/{max_retries}): {e}")
            time.sleep(1)
    return False

# -------------- Session State 初始化 --------------
def init_state():
    if "participant_id" not in st.session_state:
        st.session_state.participant_id = "P_" + str(random.randint(100000, 999999))
    if "demographics_done" not in st.session_state:
        st.session_state.demographics_done = False
    if "trial_order" not in st.session_state:
        order = STIMULI[:]
        random.shuffle(order)
        st.session_state.trial_order = order[:TRIALS_PER_PARTICIPANT]
    if "trial_idx" not in st.session_state:
        st.session_state.trial_idx = 0
    if "trial_start_time" not in st.session_state:
        st.session_state.trial_start_time = None
    if "form_unlocked_time" not in st.session_state:
        st.session_state.form_unlocked_time = None

init_state()
ws = open_worksheet()

# ------------------- UI：标题 -------------------
st.title("Urban Acoustic Comfort Study")
st.caption("Please wear headphones in a quiet environment.")

# ---------------- Demographics（只填一次） ----------------
if not st.session_state.demographics_done:
    st.subheader("Step 1: Consent & Setup")

    st.write(
        "By proceeding, you confirm you are willing to give consent to your anonymous responses being used for research."
    )
    consent = st.checkbox("I consent to participate.")

    colA, colB = st.columns(2)
    with colA:
        age = st.number_input("Age", min_value=1, max_value=100, step=1, value=25)
    with colB:
        gender = st.selectbox(
            "Gender",
            ["", "Female", "Male", "Non-binary", "Prefer not to say", "Other"]
        )

    st.write("Please put on your headphones and listen to the test audio and try not to adjust the volume again during the Trials.")
    st.audio("t_pinknoise_6s.wav")

    disabled = not (consent and gender)
    if st.button("Begin trials", disabled=disabled):
        st.session_state.base_info = {
            "age": int(age),
            "gender": gender,
        }
        st.session_state.demographics_done = True
        st.rerun()

# ----------------- Trials 循环 -----------------
if st.session_state.demographics_done and st.session_state.trial_idx < len(st.session_state.trial_order):

    i = st.session_state.trial_idx
    stim = st.session_state.trial_order[i]

    st.subheader(f"Step 2: Trial {i+1} of {len(st.session_state.trial_order)}")

    col1, col2 = st.columns(2)
    with col1:
        st.image(stim["image"], use_container_width=True, caption=f"Stimulus {stim['id']}")
    with col2:
        st.audio(stim["audio"])

    if st.session_state.trial_start_time is None:
        st.session_state.trial_start_time = time.time()
    elapsed = time.time() - st.session_state.trial_start_time
    ready = elapsed >= MIN_LISTEN_SECONDS

    if not ready:
        st.info(f"Please listen to the sound before answering.")
        st.progress(min(1.0, elapsed / MIN_LISTEN_SECONDS))

    # ------------------- 打分部分 -------------------
    st.markdown("Acoustic comfort (0.00–1.00)")
    st.caption("What's your overall impression after viewing the image and listening to the sound?")
    comfort = st.slider("", 0.0, 1.0, 0.5, 0.01, key=f"comfort_{i}")
    st.markdown("Pleasantness (0.00–1.00)")
    st.caption("How you feel at this moment?")
    pleasantness = st.slider("", 0.0, 1.0, 0.5, 0.01, key=f"pleasantness_{i}")
    st.markdown("Soundscape Appropriateness (0.00–1.00)")
    st.caption("Soundscape appropriateness (SA) was proposed as an indicator of whether a soundscape is suitable for a place.  \n:gray[Rated from 0.00(unsuitable) to 1.00(suitable)]")
    match = st.slider("", 0.0, 1.0, 0.5, 0.01, key=f"match_{i}")

    all_sound_types = [
        "Birdsong", "Wind", "Water", 
        "Human voice", "Car", "Bicycle", "Airplane/Helicopter", "Construction noise", "Music", "Other"
    ]
    sound_types = st.multiselect(
        "Which kinds of sound did you hear? (Select-all-that-apply)",
        all_sound_types,
        key=f"multiselect_{i}"
    )

    ratings = {}
    if sound_types:
        st.write("Please rate your satisfaction with the selected sound(s):")
        for sound in sound_types:
            ratings[sound] = st.slider(
                f"Satisfaction of {sound} ",
                min_value=0.0,
                max_value=1.0,
                value=0.5,
                step=0.01,
                key=f"satisfaction_{sound}_{i}"
            )

    # ------------------- 提交按钮 -------------------
    submitted = st.button("Submit this trial", disabled=not ready)

    if submitted:
        if st.session_state.form_unlocked_time is None:
            st.session_state.form_unlocked_time = st.session_state.trial_start_time + MIN_LISTEN_SECONDS
        rt_ms = int((time.time() - st.session_state.form_unlocked_time) * 1000)

        heard = {s: 9 for s in all_sound_types}
        for s in sound_types:
            heard[s] = ratings.get(s, 9)

        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            st.session_state.participant_id,
            i,
            stim["id"],
            stim["image"],
            stim["audio"],
            st.session_state.base_info["age"],
            st.session_state.base_info["gender"],
            float(comfort),
            float(pleasantness),
            float(match),
            heard["Birdsong"],
            heard["Wind"],
            heard["Water"],
            heard["Human voice"],
            heard["Car"],
            heard["Bicycle"],
            heard["Airplane/Helicopter"],
            heard["Construction noise"],
            heard["Music"],
            heard["Other"],
            rt_ms
        ]

        ok = append_row_with_retry(ws, row)
        if ok:
            st.success("✅ Trial submitted.")
        else:
            st.error("❌ Failed to write to Google Sheets.")

        # ------------------- 清理 widget 状态 -------------------
        st.session_state.pop(f"comfort_{i}", None)
        st.session_state.pop(f"pleasantness_{i}", None)
        st.session_state.pop(f"match_{i}", None)
        st.session_state.pop(f"multiselect_{i}", None)
        for s in all_sound_types:
            st.session_state.pop(f"satisfaction_{s}_{i}", None)

        # 下一试
        st.session_state.trial_idx += 1
        st.session_state.trial_start_time = None
        st.session_state.form_unlocked_time = None
        st.rerun()

# ----------------- 结束页 -----------------
if st.session_state.demographics_done and st.session_state.trial_idx >= len(st.session_state.trial_order):
    st.subheader("All done — thank you!")
    st.write("Your responses have been recorded.")
    st.write(f"Participant ID: **{st.session_state.participant_id}**")













