import os
import json
import shutil
import time
from datetime import datetime
from multiprocessing import get_logger

import pandas as pd
from flask import session

STATIC_FOLDER = "config"
GLOBAL_SESSION_FILE = os.path.join(STATIC_FOLDER, "global_sessions.json")
UPLOAD_FOLDER = "uploads"
DEBUG_FOLDER = "debug_output"

HEARTBEAT_TIMEOUT_SECONDS = 5 * 60  # 5 minutes

def get_global_session_list():
    if os.path.exists(GLOBAL_SESSION_FILE):
        try:
            with open(GLOBAL_SESSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_global_session_list(data):
    with open(GLOBAL_SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# === Helper Functions for Session and Answer Key Management ===
def get_session_data():
    try:
        config_path = get_session_path("config")
        session_file = os.path.join(config_path, "session_data.json")
        if os.path.exists(session_file):
            with open(session_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except (ValueError, FileNotFoundError):
        return {}
    except json.JSONDecodeError:
        return {}
    return {}


# === ฟังก์ชัน Helper ใหม่ สำหรับจัดการ Session Path ===
def get_session_path(folder_type):
    if "session_id" not in session:
        raise ValueError("Cannot get session path without an active session.")
    session_id = session["session_id"]
    base_folder = ""
    if folder_type == "uploads":
        base_folder = UPLOAD_FOLDER
    elif folder_type == "debug_output":
        base_folder = DEBUG_FOLDER
    elif folder_type == "config":
        base_folder = STATIC_FOLDER
    else:
        raise ValueError(f"Unknown folder type: {folder_type}")
    session_specific_path = os.path.join(base_folder, session_id)
    if not os.path.exists(session_specific_path):
        os.makedirs(session_specific_path)
        get_logger().info(f"Created session directory: {session_specific_path}")
    return session_specific_path


def _cleanup_session_directories(session_id: str):
    paths_to_delete = [
        os.path.join(UPLOAD_FOLDER, session_id),
        os.path.join(DEBUG_FOLDER, session_id),
        os.path.join(STATIC_FOLDER, session_id),
    ]
    for path in paths_to_delete:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
                get_logger().info(f"Removed idle session directory: {path}")
            except Exception as e:
                get_logger().error(f"Failed to delete directory {path}. Reason: {e}")


def _cleanup_inactive_sessions_loop():
    check_interval = 60  # seconds
    while True:
        try:
            global_sessions = get_global_session_list()
            active_sessions = global_sessions.get("active_sessions", {})
            if not active_sessions:
                time.sleep(check_interval)
                continue

            now_ts = time.time()
            to_remove = []
            for sid, meta in list(active_sessions.items()):
                last_activity_iso = meta.get("last_activity")
                try:
                    last_ts = datetime.fromisoformat(last_activity_iso).timestamp() if last_activity_iso else 0
                except Exception:
                    last_ts = 0
                if now_ts - last_ts > HEARTBEAT_TIMEOUT_SECONDS:
                    to_remove.append(sid)

            for sid in to_remove:
                get_logger().info(f"Cleaning up inactive session: {sid}")
                _cleanup_session_directories(sid)
                active_sessions.pop(sid, None)

            if to_remove:
                global_sessions["active_sessions"] = active_sessions
                save_global_session_list(global_sessions)
        except Exception as e:
            get_logger().error(f"Cleanup loop error: {e}")
        finally:
            time.sleep(check_interval)





def save_session_data(data):
    try:
        config_path = get_session_path("config")
        session_file = os.path.join(config_path, "session_data.json")
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except ValueError:
        get_logger().error("Attempted to save session data without an active session.")


def load_answer_key(mode):
    try:
        config_path = get_session_path("config")
        key_path = os.path.join(config_path, f"answer_key_{mode}.csv")
    except ValueError:
        return None, "No active session to load answer key from."

    if not os.path.exists(key_path):
        return None, f"ไม่พบไฟล์เฉลยสำหรับโหมด {mode}"

    key_dict = {}
    try:
        df = pd.read_csv(key_path, header=None, dtype=str)
        for _, row in df.iterrows():
            q_num = int(row[0])
            answers_str = str(row[1])
            if mode == "single":
                key_dict[q_num] = int(answers_str)
            else:  # multi
                key_dict[q_num] = {int(ans) for ans in answers_str.split("&")}
        return key_dict, None
    except Exception as e:
        return None, f"ผิดพลาดในการอ่านไฟล์เฉลย {mode}: {e}"

def process_data(student_id, student_names, answered_data):
    score = sum(
        1 for data in answered_data.values() if data.get("status") == "correct"
    )
    first_name, last_name = student_names.get(str(student_id).strip(), ("ไม่พบชื่อ", "-"))

    return first_name, last_name, score