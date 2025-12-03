import cv2
import math
import time
import numpy as np
import streamlit as st
import mediapipe as mp
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL, CoInitialize
from comtypes.client import CreateObject
from pycaw.pycaw import IAudioEndpointVolume, IMMDeviceEnumerator

# ==========================================
# 1. SETUP & CONFIGURATION
# ==========================================

st.set_page_config(layout="wide", page_title="Hand Gesture Mic Control")

# Constants
PINCH_THRESHOLD = 30     
MIN_DIST = 30            
MAX_DIST = 200           
SMOOTHING = 5            

# Load MediaPipe
@st.cache_resource
def load_mediapipe():
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7
    )
    mp_draw = mp.solutions.drawing_utils
    return hands, mp_draw

hands, mp_draw = load_mediapipe()

# --- AUDIO SETUP (Run once per session) ---
def get_mic_interface():
    try:
        # Initialize COM library
        CoInitialize()
        CLSID_MMDeviceEnumerator = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
        enumerator = CreateObject(CLSID_MMDeviceEnumerator, interface=IMMDeviceEnumerator)
        # 1 = Mic (eCapture), 0 = Multimedia (eConsole)
        device = enumerator.GetDefaultAudioEndpoint(1, 0)
        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception as e:
        return None

# ==========================================
# 2. SIDEBAR CONTROLS
# ==========================================

with st.sidebar:
    st.header("Settings")
    cam_index = st.selectbox("Select Camera Index", [0, 1, 2], index=0)
    
    st.header("Manual Controls")
    
    # We create a temporary connection just for button clicks
    def manual_change(change):
        vc = get_mic_interface()
        if vc:
            try:
                curr = vc.GetMasterVolumeLevelScalar()
                vc.SetMasterVolumeLevelScalar(min(max(curr + change, 0.0), 1.0), None)
            except: pass

    def manual_mute():
        vc = get_mic_interface()
        if vc:
            try:
                state = vc.GetMute()
                vc.SetMute(not state, None)
            except: pass

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("Vol +10%"): manual_change(0.1)
    with col_b2:
        if st.button("Vol -10%"): manual_change(-0.1)
        
    if st.button("Toggle Mute"): manual_mute()

# ==========================================
# 3. MAIN DASHBOARD
# ==========================================

st.title("Microphone volume control using hand gestures")
st.markdown("**NAME:** HARI KRISHNA")
st.markdown("**MENTOR:** Dr. D. BHANU PRAKASH")
st.markdown("---")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Dashboard")
    
    if 'run_camera' not in st.session_state:
        st.session_state.run_camera = False

    def toggle_camera_state():
        st.session_state.run_camera = not st.session_state.run_camera

    btn_text = "STOP CAMERA" if st.session_state.run_camera else "START CAMERA"
    st.button(btn_text, on_click=toggle_camera_state)

    st.markdown("### Real-time Data")
    vol_metric = st.empty()
    dist_metric = st.empty()
    status_msg = st.empty()

with col2:
    st.subheader("Camera Feed")
    video_placeholder = st.empty()

# ==========================================
# 4. STABLE CAMERA LOOP
# ==========================================

if st.session_state.run_camera:
    # 1. Open Camera
    cap = cv2.VideoCapture(cam_index)
    
    if not cap.isOpened():
        st.error(f"Error: Could not open Camera {cam_index}.")
        st.session_state.run_camera = False
    else:
        # 2. INITIALIZE AUDIO ONCE (CRITICAL FIX)
        # We do this OUTSIDE the loop to prevent memory crashes
        vc = get_mic_interface()
        
        if vc is None:
            st.warning("Audio system not detected, but camera will run.")

        status_msg.info("Camera Active.")
        
        while st.session_state.run_camera:
            ret, frame = cap.read()
            if not ret:
                st.warning("Camera disconnected.")
                break
            
            # Processing
            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb_frame)
            
            current_dist_px = 0
            is_pinched = False
            
            if results.multi_hand_landmarks:
                for hand_lms in results.multi_hand_landmarks:
                    mp_draw.draw_landmarks(frame, hand_lms, mp.solutions.hands.HAND_CONNECTIONS)
                    
                    # Landmarks
                    x1 = int(hand_lms.landmark[4].x * w)
                    y1 = int(hand_lms.landmark[4].y * h)
                    x2 = int(hand_lms.landmark[8].x * w)
                    y2 = int(hand_lms.landmark[8].y * h)
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    
                    # Draw
                    cv2.circle(frame, (x1, y1), 10, (255, 0, 255), cv2.FILLED)
                    cv2.circle(frame, (x2, y2), 10, (255, 0, 255), cv2.FILLED)
                    cv2.line(frame, (x1, y1), (x2, y2), (255, 0, 255), 3)
                    
                    length = math.hypot(x2 - x1, y2 - y1)
                    current_dist_px = int(length)
                    
                    # Logic using the EXISTING 'vc' object
                    if vc:
                        try:
                            if length < PINCH_THRESHOLD:
                                cv2.circle(frame, (cx, cy), 15, (0, 255, 0), cv2.FILLED)
                                cv2.putText(frame, "MUTED", (50, 50), cv2.FONT_HERSHEY_COMPLEX, 1, (0, 0, 255), 3)
                                
                                # Optimize: only write if state changes
                                if not vc.GetMute():
                                    vc.SetMute(1, None)
                                is_pinched = True
                            else:
                                if vc.GetMute():
                                    vc.SetMute(0, None)
                                is_pinched = False
                                
                                vol_per = np.interp(length, [MIN_DIST, MAX_DIST], [0, 100])
                                vol_per = SMOOTHING * round(vol_per / SMOOTHING)
                                vc.SetMasterVolumeLevelScalar(vol_per / 100, None)
                        except:
                            # If connection lost, try to reconnect once (optional complexity omitted for stability)
                            pass

            # Update Metrics
            if vc:
                try:
                    curr_vol = int(vc.GetMasterVolumeLevelScalar() * 100)
                    vol_metric.metric("Mic Volume", f"{curr_vol}%")
                except:
                    vol_metric.metric("Mic Volume", "--")
            
            dist_metric.metric("Finger Distance", f"{current_dist_px} px")
            
            if is_pinched:
                status_msg.error("MUTED")
            else:
                status_msg.success("LISTENING")

            # Display Video
            video_placeholder.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), channels="RGB", width=500)
            
            # --- IMPORTANT: STABILITY DELAY ---
            # This prevents the loop from hogging 100% CPU and crashing Streamlit
            time.sleep(0.03)

        cap.release()
        cv2.destroyAllWindows()
        st.write("Camera Stopped.")