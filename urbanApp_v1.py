import time
import random
from datetime import datetime

import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import APIError

# ------------------- CONFIG -------------------
GOOGLE_SHEET_NAME = "UrbanSoundscapeData"   # 你的 Google 表格名
WORKSHEET_INDEX = 0                         # 第几个工作表（0 表示第一个）

STIMULI = [
    {"id": "S01", "image": "i_qeop_3.jpg", "audio": "a_3_garden.wav"},
    {"id": "S02", "image": "i_qeop_2.jpg", "audio": "a_2_spring music.wav"},
    {"id": "S03", "image": "i_qeop_1.jpg", "audio": "a_1_east village.wav"},
]

TRIALS_PER_PARTICIPANT = min(3, len(STIMULI))
MIN_LISTEN_SECONDS = 3
# ----------------------------------------------

st.set_page_config(page_title="Soundscape Perception Test", page_icon="🎧", layout="centered")

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
            time.sleep(2 ** i)
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
st.title("Urban Soundscape & Visual Comfort Study")
st.caption("Please wear headphones in a quiet environment.")

# ---------------- Demographics ----------------
if not st.session_state.demographics_done:
    st.subheader("Step 1: Consent & Setup")

    st.write(
        "By proceeding, you confirm you are 18+ and consent to your anonymous responses being used for research."
    )
    consent = st.checkbox("I consent to participate.")

    colA, colB = st.columns(2)
    with colA:
        age = st.number_input("Age", min_value=18, max_value=100, step=1, value=25)
    with colB:
        gender = st.selectbox(
            "Gender",
            ["", "Female", "Male", "Non-binary", "Prefer not to say", "Other"]
        )

    st.write(
        "Please put on your headphones and listen to the test audio. Adjust the volume to a level that is clear but not uncomfortable, and do not change the volume during the rest of the trials."
    )
    st.audio("t_pinknoise.wav")

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
        st.info(f"Please listen to the sound for at least {MIN_LISTEN_SECONDS} seconds before answering.")
        st.progress(min(1.0, elapsed / MIN_LISTEN_SECONDS))

    with st.form(key=f"form_trial_{i}"):
        comfort = st.slider("Acoustic comfort (0–1)", 0.0, 1.0, 0.5, 0.01)
        pleasantness = st.slider("Pleasantness (0–1)", 0.0, 1.0, 0.5, 0.01)
        match = st.slider("Soundscape Appropriateness (0–1)", 0.0, 1.0, 0.5, 0.01)

        sound_types = st.multiselect(
            "Which sound source types did you hear?",
            ["Traffic", "Birds/Nature", "People/Talking", "Wind", "Construction/Mechanical", "Music", "Other"]
        )

        # 针对每种选择的声音，额外显示满意度
        satisfaction = {}
        for s in sound_types:
            satisfaction[s] = st.slider(f"Satisfaction with {s} (0–1)", 0.0, 1.0, 0.5, 0.01, key=f"satis_{i}_{s}")

        submitted = st.form_submit_button("Submit this trial")

    if submitted:
        if st.session_state.form_unlocked_time is None:
            st.session_state.form_unlocked_time = st.session_state.trial_start_time + MIN_LISTEN_SECONDS
        rt_ms = int((time.time() - st.session_state.form_unlocked_time) * 1000)

        heard = {s: 0 for s in ["Traffic", "Birds/Nature", "People/Talking", "Wind", "Construction/Mechanical", "Music", "Other"]}
        satis_scores = {s: "" for s in heard.keys()}

        for s in sound_types:
            heard[s] = 1
            satis_scores[s] = float(satisfaction.get(s, ""))

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
            heard["Traffic"], satis_scores["Traffic"],
            heard["Birds/Nature"], satis_scores["Birds/Nature"],
            heard["People/Talking"], satis_scores["People/Talking"],
            heard["Wind"], satis_scores["Wind"],
            heard["Construction/Mechanical"], satis_scores["Construction/Mechanical"],
            heard["Music"], satis_scores["Music"],
            heard["Other"], satis_scores["Other"],
            rt_ms
        ]

        ok = append_row_with_retry(ws, row)
        if ok:
            st.success("✅ Trial submitted.")
        else:
            st.error("❌ Failed to write to Google Sheets. You can retry by clicking 'Submit' again.")

        st.session_state.trial_idx += 1
        st.session_state.trial_start_time = None
        st.session_state.form_unlocked_time = None
        st.rerun()

# ----------------- 结束页 -----------------
if st.session_state.demographics_done and st.session_state.trial_idx >= len(st.session_state.trial_order):
    st.subheader("All done — thank you!")
    st.write("Your responses have been recorded.")
    st.write(f"Participant ID: **{st.session_state.participant_id}**")
