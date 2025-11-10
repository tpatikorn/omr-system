import io
import json
import os
import secrets
import shutil
import time
import traceback
import uuid
from datetime import datetime
from queue import Queue
import pandas as pd
from PIL import Image
from flask import (
    Flask,
    request,
    render_template,
    send_file,
    jsonify,
    send_from_directory,
    Response,
    session,
    redirect,
    url_for,
)
from flask_compress import Compress

from manager.file_manager import clear_folder
from manager.image_util import convert_pdf_to_images, create_web_optimized_image, clean_image_file
from manager.omr import OMRSystemFinal
from manager.logging_manager import setup_logging
from manager.session_manager import get_session_path, get_session_data, get_global_session_list, save_global_session_list, \
    _cleanup_inactive_sessions_loop, process_data, load_answer_key, save_session_data
from manager.web_util import get_base_url, get_local_ip

import threading

# --- โฟลเดอร์สำหรับเก็บไฟล์ ---
UPLOAD_FOLDER = "uploads"
DEBUG_FOLDER = "debug_output"
STATIC_FOLDER = "config"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}
CLEANUP_THREAD_STARTED = False

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # สำหรับ session management

# ตั้งค่า Compression
app.config['COMPRESS_MIMETYPES'] = [
    'text/html',
    'text/css',
    'text/xml',
    'text/javascript',
    'application/json',
    'application/javascript',
    'application/xml+rss',
    'application/atom+xml',
    'image/svg+xml'
]
app.config['COMPRESS_LEVEL'] = 6  # ระดับการบีบอัด (1-9, 6 เป็นค่าเริ่มต้นที่ดี)
app.config['COMPRESS_MIN_SIZE'] = 500  # บีบอัดเฉพาะไฟล์ที่ใหญ่กว่า 500 bytes

# เปิดใช้งาน Compression
compress = Compress(app)

app_logger = setup_logging(app)  # <--- ใช้ระบบ logging ใหม่
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# สร้างโฟลเดอร์ถ้ายังไม่มี
for folder in [UPLOAD_FOLDER, DEBUG_FOLDER, STATIC_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)


class MessageAnnouncer:
    def __init__(self):
        self.listeners = []

    def listen(self):
        q = Queue(maxsize=5)
        self.listeners.append(q)
        return q

    def announce(self, msg):
        for i in reversed(range(len(self.listeners))):
            try:
                self.listeners[i].put_nowait(msg)
            except Exception:
                del self.listeners[i]


announcer = MessageAnnouncer()
omr_system = OMRSystemFinal()


def _utcnow_iso():
    return datetime.now().isoformat()

@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    try:
        if "session_id" not in session:
            return jsonify({"success": False, "error": "No active session"}), 400

        global_sessions = get_global_session_list()
        active_sessions = global_sessions.get("active_sessions", {})
        sid = session["session_id"]

        if sid not in active_sessions:
            # Re-register if missing
            active_sessions[sid] = {
                "created_at": _utcnow_iso(),
                "device_type": session.get("device_type", "unknown"),
                "last_activity": _utcnow_iso(),
            }
        else:
            active_sessions[sid]["last_activity"] = _utcnow_iso()

        global_sessions["active_sessions"] = active_sessions
        save_global_session_list(global_sessions)
        return jsonify({"success": True})
    except Exception as e:
        app_logger.error(f"Heartbeat error: {e}")
        return jsonify({"success": False}), 500


@app.route("/toggle_debug", methods=["POST"])
def toggle_debug():
    """เปิด/ปิด debug mode เพื่อเพิ่มความเร็วในการประมวลผล"""
    data = request.get_json()
    debug_enabled = data.get("debug", False)
    omr_system.debug_mode = debug_enabled
    app_logger.info(f"Debug mode {'enabled' if debug_enabled else 'disabled'}")
    return jsonify({"debug_mode": omr_system.debug_mode})


# === API สำหรับโหมด 1 คำตอบ (Single-Answer) ===
@app.route("/upload_answer_key_single", methods=["POST"])
def upload_answer_key_single():
    file = request.files.get("answer_key")
    if not file:
        return jsonify({"message": "No file provided"}), 400

    try:
        config_path = get_session_path("config")
        filepath = os.path.join(config_path, "answer_key_single.csv")
        file.save(filepath)
        app_logger.info(
            f"Single mode answer key uploaded for session {session['session_id']}: {file.filename}"
        )
        return jsonify({"success": True, "filename": file.filename})
    except ValueError:
        return jsonify({"error": "No active session"}), 400


@app.route("/save_answer_key_single", methods=["POST"])
def save_answer_key_single():
    try:
        data = request.get_json()
        csv_content = data.get("csv_content", "")
        filename = data.get("filename", "manual_answer_key_single.csv")

        config_path = get_session_path("config")
        answer_key_path = os.path.join(config_path, "answer_key_single.csv")

        with open(answer_key_path, "w", encoding="utf-8") as f:
            f.write(csv_content)

        app_logger.info(
            f"Single mode answer key saved for session {session['session_id']}: {filename}"
        )

        return jsonify(
            {
                "success": True,
                "message": "Answer key saved successfully",
                "filename": filename,
            }
        )
    except ValueError:
        return jsonify({"error": "No active session"}), 400
    except Exception as e:
        app_logger.error(f"Error saving single mode answer key: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/process_single", methods=["POST"])
def process_single():
    answer_key, err = load_answer_key("single")
    if err:
        return jsonify({"error": err}), 400

    try:
        session_upload_path = get_session_path("uploads")
        session_debug_path = get_session_path("debug_output")
        session_config_path = get_session_path("config")
    except ValueError:
        return jsonify({"error": "No active session"}), 400

    student_list_path = os.path.join(session_config_path, "student_list.csv")
    student_names = {}
    if os.path.exists(student_list_path):
        try:
            # Read with skipinitialspace to handle spaces after commas
            df_students = pd.read_csv(student_list_path, header=None, skipinitialspace=True)
            # Build student_names dict for lookup (first name + last name)
            student_names = dict(
                zip(
                    df_students[0].astype(str).str.strip(),
                    (df_students[1].astype(str).str.strip(), df_students[2].astype(str).str.strip())
                )
            )
        except Exception as e:
            app_logger.warning(f"Could not load student names: {e}")

    student_sheets_files = sorted(
        [f for f in os.listdir(session_upload_path) if allowed_file(f)]
    )

    if not student_sheets_files:
        return jsonify({"error": "No student answer sheets to process"}), 400

    results = []
    seen_student_ids = {}  # ติดตามรหัสนักศึกษาที่เจอแล้ว {student_id: [list of filenames]}

    session_data = get_session_data()
    session_data["single_detailed_answers"] = {}

    for filename in student_sheets_files:
        # ใช้รูปภาพต้นฉบับสำหรับการประมวลผล (ไม่ใช่เวอร์ชันเว็บ)
        original_filename = filename
        if filename.startswith("web_"):
            # ถ้าเป็นไฟล์เวอร์ชันเว็บ ให้หาไฟล์ต้นฉบับ
            original_filename = filename[4:]  # ตัด "web_" ออก
            if not os.path.exists(os.path.join(session_upload_path, original_filename)):
                continue  # ถ้าไม่มีไฟล์ต้นฉบับ ข้าม
        elif os.path.exists(os.path.join(session_upload_path, f"web_{filename}")):
            # ถ้ามีเวอร์ชันเว็บอยู่แล้ว ข้ามไฟล์ต้นฉบับ (ป้องกันการประมวลผลซ้ำ)
            continue
            
        filepath = os.path.join(session_upload_path, original_filename)
        try:
            with open(filepath, "rb") as f:
                image_bytes = f.read()

            student_id, answered_data, h_file = omr_system.find_and_process_sheet(
                image_bytes,
                original_filename,
                mode="single",
                single_answer_key=answer_key,
                session_debug_folder=session_debug_path,  # ส่ง Path ของ session ปัจจุบัน
            )

            serializable_answers = {}
            multiple_answers_count = 0  # นับจำนวนข้อที่กาหลายคำตอบ
            for q_num, data in answered_data.items():
                serializable_answers[q_num] = {
                    "answers": list(data.get("answers", set())),
                    "status": data.get("status", "incorrect"),
                    "has_multiple_answers": data.get("has_multiple_answers", False),
                }
                if data.get("has_multiple_answers", False):
                    multiple_answers_count += 1
            session_data["single_detailed_answers"][student_id] = serializable_answers

            first_name, last_name, score = process_data(student_id, student_names, answered_data)
            # ตรวจสอบรหัสซ้ำ
            is_duplicate = False
            if str(student_id) in seen_student_ids:
                is_duplicate = True
                seen_student_ids[str(student_id)].append(original_filename)
                app_logger.warning(f"Duplicate student ID detected: {student_id} in files {seen_student_ids[str(student_id)]}")
            else:
                seen_student_ids[str(student_id)] = [original_filename]
            
            results.append(
                {
                    "student_file": original_filename,
                    "student_id": student_id,
                    "student_name": f"{first_name} {last_name}".strip(),  # แสดงชื่อ+นามสกุลในคอลัมเดียว
                    "fname": first_name,
                    "lname": last_name,
                    "score": score,
                    "total": len(answer_key),
                    "image_url": f"/debug_output/{session['session_id']}/{h_file}",  # ใช้รูปภาพที่บีบอัดแล้ว
                    "multiple_answers_count": multiple_answers_count,  # เพิ่มข้อมูลจำนวนข้อที่กาหลายคำตอบ
                    "has_issues": multiple_answers_count > 0 or is_duplicate,  # มีปัญหาหรือไม่ (รวมรหัสซ้ำ)
                    "is_duplicate": is_duplicate,  # เพิ่มแฟล็กรหัสซ้ำ
                }
            )
        except Exception as e:
            app_logger.error(
                f"ERROR processing {original_filename}: {e} | {traceback.format_exc()}"
            )
            results.append(
                {
                    "student_file": original_filename,
                    "student_id": "ERROR",
                    "student_name": "ข้อผิดพลาด",
                    "score": "Processing Error",
                    "total": len(answer_key) if answer_key else 0,
                    "image_url": f"/uploads/{session['session_id']}/{original_filename}",
                }
            )

    # เรียงผลลัพธ์ตามรหัสนักศึกษาก่อนบันทึก
    # แยกเป็น 2 กลุ่ม: ไม่พบชื่อ/รหัสอ่านไม่ได้ (ไม่ sort) และ พบชื่อ+รหัสปกติ (sort ตามรหัส)
    not_found_group = []  # กลุ่มที่ไม่พบชื่อหรือรหัสอ่านไม่ได้ - ไม่ sort
    found_group = []      # กลุ่มที่พบชื่อและรหัสปกติ - sort ตามรหัส
    
    for result in results:
        student_name = result.get("student_name", "")
        student_id = result.get("student_id", "")
        has_issues = result.get("has_issues", False)  # ตรวจสอบว่ามีปัญหาการกาหลายคำตอบหรือไม่
        
        # ตรวจสอบว่าพบชื่อและรหัสนักศึกษาหรือไม่
        is_name_not_found = (
            student_name == "ไม่พบชื่อ" or 
            student_name == "ไม่พบชื่อในรายชื่อ" or 
            student_name == "ข้อผิดพลาด" or
            not student_name or 
            student_name.strip() == ""
        )
        
        is_id_invalid = (
            student_id == "Error Reading ID" or
            student_id == "ERROR" or
            "-" in str(student_id) or  # รหัสที่อ่านไม่ครบ เช่น "12345-7890"
            not student_id or
            str(student_id).strip() == ""
        )
        
        # ถ้าไม่พบชื่อหรือรหัสอ่านไม่ได้หรือมีปัญหาการกาหลายคำตอบ ให้ใส่ในกลุ่มไม่ sort
        if is_name_not_found or is_id_invalid or has_issues:
            not_found_group.append(result)
        else:
            found_group.append(result)
    
    # sort เฉพาะกลุ่มที่พบชื่อและรหัสปกติ
    found_group_sorted = sorted(found_group, key=lambda x: str(x.get("student_id", "")).lower())
    
    # รวมผลลัพธ์: กลุ่มไม่พบชื่อ/รหัสอ่านไม่ได้/มีปัญหาก่อน (ไม่ sort) + กลุ่มพบชื่อ+รหัสปกติ (sort แล้ว)
    results = not_found_group + found_group_sorted
    
    session_data["single_results"] = results
    save_session_data(session_data)

    # สร้าง DataFrame สำหรับ export
    students = []
    if os.path.exists(student_list_path):
        try:
            # df_students is already loaded above
            for idx, row in df_students.iterrows():
                student_id = str(row[0]).strip()
                name = str(row[1]).strip()
                if name and " " in name:
                    fname, lname = name.split(" ", 1)
                else:
                    fname, lname = name, ""
                group_code = str(row[2]).strip() if len(row) > 2 else ""
                students.append({
                    "student_id": student_id,
                    "fname": fname,
                    "lname": lname,
                    "group_code": group_code
                })
        except Exception as e:
            app_logger.warning(f"Could not build students list: {e}")

    export_rows = []
    for s in students:
        # ตรวจสอบว่ามี student_id จริง
        if "student_id" in s and s["student_id"]:
            export_rows.append({
                "student_id": s["student_id"],
                "fname": s.get("fname", ""),
                "lname": s.get("lname", ""),
                "group_code": s.get("group_code", ""),
                "score": next((r["score"] for r in results if r["student_id"] == s["student_id"]), "")
            })
    if not export_rows:
        return jsonify({"success": False, "error": "ไม่พบ student_id ในรายชื่อ"}), 400
    df = pd.DataFrame(export_rows)
    if "student_id" in df.columns:
        df = df.sort_values(by=["student_id"])

    return jsonify({"results": results})


# === API สำหรับโหมดหลายคำตอบ (Multi-Answer) ===
@app.route("/upload_answer_key_multi", methods=["POST"])
def upload_answer_key_multi():
    file = request.files.get("answer_key")
    if not file:
        return jsonify({"message": "No file provided"}), 400

    content = file.stream.read().decode("utf-8")
    file.stream.seek(0)
    if "&" not in content:
        return (
            jsonify({"message": "ไฟล์เฉลยนี้ไม่ใช่สำหรับโหมดหลายคำตอบ (ต้องมีคำตอบที่คั่นด้วย &)"}),
            400,
        )

    try:
        config_path = get_session_path("config")
        filepath = os.path.join(config_path, "answer_key_multi.csv")
        file.save(filepath)
        app_logger.info(
            f"Multi mode answer key uploaded for session {session['session_id']}: {file.filename}"
        )
        return jsonify({"success": True, "filename": file.filename})
    except ValueError:
        return jsonify({"error": "No active session"}), 400


@app.route("/save_answer_key_multi", methods=["POST"])
def save_answer_key_multi():
    try:
        data = request.get_json()
        csv_content = data.get("csv_content", "")
        filename = data.get("filename", "manual_answer_key_multi.csv")

        config_path = get_session_path("config")
        answer_key_path = os.path.join(config_path, "answer_key_multi.csv")

        with open(answer_key_path, "w", encoding="utf-8") as f:
            f.write(csv_content)

        app_logger.info(
            f"Multi mode answer key saved for session {session['session_id']}: {filename}"
        )

        return jsonify(
            {
                "success": True,
                "message": "Answer key saved successfully",
                "filename": filename,
            }
        )
    except ValueError:
        return jsonify({"error": "No active session"}), 400
    except Exception as e:
        app_logger.error(f"Error saving multi mode answer key: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/process_multi", methods=["POST"])
def process_multi():
    answer_key, err = load_answer_key("multi")
    if err:
        return jsonify({"error": err}), 400

    try:
        session_upload_path = get_session_path("uploads")
        session_debug_path = get_session_path("debug_output")
        session_config_path = get_session_path("config")
    except ValueError:
        return jsonify({"error": "No active session"}), 400

    student_list_path = os.path.join(session_config_path, "student_list.csv")
    student_names = {}
    if os.path.exists(student_list_path):
        try:
            df_students = pd.read_csv(student_list_path, header=None, skipinitialspace=True)
            student_names = dict(
                zip(
                    df_students[0].astype(str).str.strip(),
                    (df_students[1].astype(str).str.strip(), df_students[2].astype(str).str.strip())
                )
            )
        except Exception as e:
            app_logger.warning(f"Could not load student names: {e}")

    student_sheets_files = sorted(
        [f for f in os.listdir(session_upload_path) if allowed_file(f)]
    )

    if not student_sheets_files:
        return jsonify({"error": "No student answer sheets to process"}), 400

    results = []
    seen_student_ids = {}  # ติดตามรหัสนักศึกษาที่เจอแล้ว {student_id: [list of filenames]}

    session_data = get_session_data()
    session_data["multi_detailed_answers"] = {}

    for filename in student_sheets_files:
        # ใช้รูปภาพต้นฉบับสำหรับการประมวลผล (ไม่ใช่เวอร์ชันเว็บ)
        original_filename = filename
        if filename.startswith("web_"):
            # ถ้าเป็นไฟล์เวอร์ชันเว็บ ให้หาไฟล์ต้นฉบับ
            original_filename = filename[4:]  # ตัด "web_" ออก
            if not os.path.exists(os.path.join(session_upload_path, original_filename)):
                continue  # ถ้าไม่มีไฟล์ต้นฉบับ ข้าม
        elif os.path.exists(os.path.join(session_upload_path, f"web_{filename}")):
            # ถ้ามีเวอร์ชันเว็บอยู่แล้ว ข้ามไฟล์ต้นฉบับ (ป้องกันการประมวลผลซ้ำ)
            continue
            
        filepath = os.path.join(session_upload_path, original_filename)
        try:
            with open(filepath, "rb") as f:
                image_bytes = f.read()

            student_id, answered_data, h_file = omr_system.find_and_process_sheet(
                image_bytes,
                original_filename,
                mode="multi",
                multi_answer_key=answer_key,
                session_debug_folder=session_debug_path,
            )

            serializable_answers = {}
            multiple_answers_count = 0  # นับจำนวนข้อที่กาหลายคำตอบ (ไม่ใช้ใน multi mode แต่เก็บไว้เพื่อความสม่ำเสมอ)
            for q_num, data in answered_data.items():
                serializable_answers[q_num] = {
                    "answers": list(data.get("answers", set())),
                    "status": data.get("status", "incorrect"),
                    "has_multiple_answers": data.get("has_multiple_answers", False),
                }
                # ใน multi mode การกาหลายคำตอบเป็นเรื่องปกติ ไม่นับเป็นปัญหา
            session_data["multi_detailed_answers"][student_id] = serializable_answers
            first_name, last_name, score = process_data(student_id, student_names, answered_data)
            
            # ตรวจสอบรหัสซ้ำ
            is_duplicate = False
            if str(student_id) in seen_student_ids:
                is_duplicate = True
                seen_student_ids[str(student_id)].append(original_filename)
                app_logger.warning(f"Duplicate student ID detected: {student_id} in files {seen_student_ids[str(student_id)]}")
            else:
                seen_student_ids[str(student_id)] = [original_filename]
            
            result_item = {
                "student_file": original_filename,
                "student_id": student_id,
                "student_name": f"{first_name} {last_name}".strip(),
                "fname": first_name,
                "lname": last_name,
                "score": score,
                "total": len(answer_key),
                "image_url": f"/debug_output/{session['session_id']}/{h_file}",
                "multiple_answers_count": 0,  # ใน multi mode ไม่นับเป็นปัญหา
                "has_issues": is_duplicate,  # ใน multi mode เฉพาะรหัสซ้ำเท่านั้นที่เป็นปัญหา
                "is_duplicate": is_duplicate,  # เพิ่มแฟล็กรหัสซ้ำ
            }
            if any(d.get("status") == "partial" for d in answered_data.values()):
                result_item["status"] = "partial"
            results.append(result_item)

        except Exception as e:
            app_logger.error(
                f"ERROR processing {original_filename}: {e} | {traceback.format_exc()}"
            )
            results.append(
                {
                    "student_file": original_filename,
                    "student_id": "ERROR",
                    "student_name": "ข้อผิดพลาด",
                    "score": "Processing Error",
                    "total": len(answer_key) if answer_key else 0,
                    "image_url": f"/uploads/{session['session_id']}/{original_filename}",
                }
            )

    # เรียงผลลัพธ์ตามรหัสนักศึกษาก่อนบันทึก
    # แยกเป็น 2 กลุ่ม: ไม่พบชื่อ/รหัสอ่านไม่ได้ (ไม่ sort) และ พบชื่อ+รหัสปกติ (sort ตามรหัส)
    not_found_group = []  # กลุ่มที่ไม่พบชื่อหรือรหัสอ่านไม่ได้ - ไม่ sort
    found_group = []      # กลุ่มที่พบชื่อและรหัสปกติ - sort ตามรหัส
    
    for result in results:
        student_name = result.get("student_name", "")
        student_id = result.get("student_id", "")
        
        # ตรวจสอบว่าพบชื่อและรหัสนักศึกษาหรือไม่
        is_name_not_found = (
            student_name == "ไม่พบชื่อ" or 
            student_name == "ไม่พบชื่อในรายชื่อ" or 
            student_name == "ข้อผิดพลาด" or
            not student_name or 
            student_name.strip() == ""
        )
        
        is_id_invalid = (
            student_id == "Error Reading ID" or
            student_id == "ERROR" or
            "-" in str(student_id) or  # รหัสที่อ่านไม่ครบ เช่น "12345-7890"
            not student_id or
            str(student_id).strip() == ""
        )
        
        # ถ้าไม่พบชื่อหรือรหัสอ่านไม่ได้ ให้ใส่ในกลุ่มไม่ sort
        if is_name_not_found or is_id_invalid:
            not_found_group.append(result)
        else:
            found_group.append(result)
    
    # sort เฉพาะกลุ่มที่พบชื่อและรหัสปกติ
    found_group_sorted = sorted(found_group, key=lambda x: str(x.get("student_id", "")).lower())
    
    # รวมผลลัพธ์: กลุ่มไม่พบชื่อ/รหัสอ่านไม่ได้ก่อน (ไม่ sort) + กลุ่มพบชื่อ+รหัสปกติ (sort แล้ว)
    results = not_found_group + found_group_sorted
    
    session_data["multi_results"] = results
    save_session_data(session_data)

    # สร้าง DataFrame สำหรับ export
    students = []
    if os.path.exists(student_list_path):
        try:
            for idx, row in df_students.iterrows():
                student_id = str(row[0]).strip()
                fname = str(row[1]).strip()
                lname = str(row[2]).strip() if len(row) > 2 else ""
                group_code = str(row[3]).strip() if len(row) > 3 else ""
                students.append({
                    "student_id": student_id,
                    "fname": fname,
                    "lname": lname,
                    "group_code": group_code
                })
        except Exception as e:
            app_logger.warning(f"Could not build students list: {e}")

    export_rows = []
    for s in students:
        if "student_id" in s and s["student_id"]:
            export_rows.append({
                "student_id": s["student_id"],
                "fname": s.get("fname", ""),
                "lname": s.get("lname", ""),
                "group_code": s.get("group_code", ""),
                "score": next((r["score"] for r in results if r["student_id"] == s["student_id"]), "")
            })
    if not export_rows:
        return jsonify({"success": False, "error": "ไม่พบ student_id ในรายชื่อ"}), 400
    df = pd.DataFrame(export_rows)
    if "student_id" in df.columns:
        df = df.sort_values(by=["student_id"])

    return jsonify({"results": results})



# Middleware สำหรับ log การเข้าถึง
@app.before_request
def log_request_info():
    # กรองคำขอที่ไม่จำเป็นต้อง log
    skip_paths = ["/favicon.ico", "/static/", "/uploads/"]
    if not any(request.path.startswith(path) for path in skip_paths):
        app_logger.info(
            f"Request: {request.method} {request.url} from {request.remote_addr}"
        )


@app.after_request
def log_response_info(response):
    # กรองการ log response สำหรับ static files
    skip_paths = ["/favicon.ico", "/static/", "/uploads/"]
    if not any(request.path.startswith(path) for path in skip_paths):
        app_logger.info(
            f"Response: {response.status_code} for {request.method} {request.url}"
        )
    
    # เพิ่ม Cache-Control headers สำหรับ static files
    if any(request.path.startswith(path) for path in ["/static/", "/uploads/", "/debug_output/"]):
        # Cache static files และรูปภาพเป็นเวลา 1 ชั่วโมง
        response.headers['Cache-Control'] = 'public, max-age=3600'
        response.headers['Vary'] = 'Accept-Encoding'
    
    return response


@app.errorhandler(Exception)
def handle_exception(e):
    app_logger.error(f"Unhandled exception: {str(e)}")
    app_logger.error(traceback.format_exc())
    return jsonify({"error": "Internal server error"}), 500


@app.route("/")
def index():
    session_id_param = request.args.get("session_id")
    if session_id_param:
        # <START> FIX 3: ใช้ global list ในการตรวจสอบ
        global_sessions = get_global_session_list()
        active_sessions = global_sessions.get("active_sessions", {})
        if session_id_param in active_sessions:
            # <END> FIX 3
            session["session_id"] = session_id_param
            session["device_type"] = "mobile"
            app_logger.info(f"Mobile device connected with session: {session_id_param}")

            # ตรวจสอบไฟล์ที่อัปโหลดไว้ใน session นี้
            try:
                config_path = get_session_path("config")
                has_answer_key_single = os.path.exists(os.path.join(config_path, "answer_key_single.csv"))
                has_answer_key_multi = os.path.exists(os.path.join(config_path, "answer_key_multi.csv"))
                has_student_list = os.path.exists(os.path.join(config_path, "student_list.csv"))
            except ValueError:
                has_answer_key_single = False
                has_answer_key_multi = False
                has_student_list = False

            return render_template(
                "index.html",
                has_answer_key_single=has_answer_key_single,
                has_answer_key_multi=has_answer_key_multi,
                has_student_list=has_student_list,
            )
        else:
            return render_template("session_rejected.html")

    user_agent = request.headers.get("User-Agent", "").lower()
    is_mobile = any(
        mobile in user_agent for mobile in ["mobile", "android", "iphone", "ipad"]
    )
    force_mobile = request.args.get("mobile") == "true"

    if (is_mobile or force_mobile) and "session_id" not in session:
        return render_template("session_rejected.html")

    if "session_id" not in session:
        session["session_id"] = secrets.token_urlsafe(32)
        session["device_type"] = "browser"

        # <START> FIX 3: บันทึก session ใหม่ลง global list
        global_sessions = get_global_session_list()
        if "active_sessions" not in global_sessions:
            global_sessions["active_sessions"] = {}

        global_sessions["active_sessions"][session["session_id"]] = {
            "created_at": datetime.now().isoformat(),
            "device_type": "browser",
            "last_activity": datetime.now().isoformat(),
        }
        save_global_session_list(global_sessions)
        # <END> FIX 3

        app_logger.info(f"New browser session created: {session['session_id']}")

    # ตรวจสอบไฟล์ที่อัปโหลดไว้ใน session นี้
    try:
        config_path = get_session_path("config")
        has_answer_key_single = os.path.exists(os.path.join(config_path, "answer_key_single.csv"))
        has_answer_key_multi = os.path.exists(os.path.join(config_path, "answer_key_multi.csv"))
        has_student_list = os.path.exists(os.path.join(config_path, "student_list.csv"))
    except ValueError:
        has_answer_key_single = False
        has_answer_key_multi = False
        has_student_list = False

    return render_template(
        "index.html",
        has_answer_key_single=has_answer_key_single,
        has_answer_key_multi=has_answer_key_multi,
        has_student_list=has_student_list,
    )


@app.route("/capture")
def capture():
    # ตรวจสอบ session ก่อนเข้าหน้า capture
    if "session_id" not in session:
        return redirect(url_for("index"))

    app_logger.info(f"User accessed capture page with session: {session['session_id']}")
    return render_template("capture.html")


@app.route("/manual")
def manual():
    """หน้าคู่มือการใช้งาน"""
    app_logger.info("User accessed manual page")
    return render_template("manual.html")


@app.route("/new_session", methods=["POST"])
def new_session():
    if "session_id" in session:
        session_id = session["session_id"]
        app_logger.info(f"Clearing all data for session: {session_id}")

        paths_to_delete = [
            os.path.join(app.config["UPLOAD_FOLDER"], session_id),
            os.path.join(DEBUG_FOLDER, session_id),
            os.path.join(STATIC_FOLDER, session_id),
        ]

        for path in paths_to_delete:
            if os.path.exists(path):
                try:
                    shutil.rmtree(path)
                    app_logger.info(f"Removed directory: {path}")
                except Exception as e:
                    app_logger.error(f"Failed to delete directory {path}. Reason: {e}")

    msg = json.dumps({"event": "clear"})
    announcer.announce(msg=f"data: {msg}\n\n")

    return jsonify({"message": "Current session data cleared. Please reload the page."})


@app.route("/get_images")
def get_images():
    images = []
    try:
        session_id = session["session_id"]
        session_upload_path = get_session_path("uploads")

        if os.path.exists(session_upload_path):
            for filename in sorted(os.listdir(session_upload_path)):
                if allowed_file(filename) and not filename.startswith("web_"):
                    # ตรวจสอบว่ามีเวอร์ชันเว็บหรือไม่
                    web_filename = f"web_{filename}"
                    web_filepath = os.path.join(session_upload_path, web_filename)
                    
                    if os.path.exists(web_filepath):
                        # ใช้เวอร์ชันเว็บสำหรับแสดงผล
                        images.append(
                            {
                                "original_name": filename,
                                "saved_name": filename,
                                "web_name": web_filename,
                                "url": f"/uploads/{session_id}/{web_filename}",
                                "original_url": f"/uploads/{session_id}/{filename}",
                            }
                        )
                    else:
                        # ใช้ไฟล์ต้นฉบับถ้าไม่มีเวอร์ชันเว็บ
                        images.append(
                            {
                                "original_name": filename,
                                "saved_name": filename,
                                "url": f"/uploads/{session_id}/{filename}",
                            }
                        )
    except ValueError:
        pass  # ไม่มี session ไม่ต้องทำอะไร
    return jsonify({"files": images})


@app.route("/stream")
def stream():
    def generate():
        messages = announcer.listen()
        while True:
            msg = messages.get()
            yield msg

    return Response(generate(), mimetype="text/event-stream")


@app.route("/upload_image", methods=["POST"])
def upload_image():
    if "files" not in request.files:
        return jsonify({"error": "No file part"}), 400

    try:
        session_id = session["session_id"]
        session_upload_path = get_session_path("uploads")
    except ValueError:
        return jsonify({"error": "No active session"}), 400

    files = request.files.getlist("files")
    uploaded_files_info = []

    for file in files:
        if file and allowed_file(file.filename):
            original_filename = file.filename
            ext = original_filename.rsplit(".", 1)[1].lower()

            if ext == "pdf":
                try:
                    pdf_bytes = file.read()
                    # ส่ง Path ของ session เข้าไปในฟังก์ชัน
                    converted_images = convert_pdf_to_images(
                        pdf_bytes, original_filename, session_upload_path
                    )

                    for image_info in converted_images:
                        uploaded_files_info.append(image_info)
                        msg = json.dumps({"event": "new_image", "data": image_info, "session_id": session_id})
                        announcer.announce(msg=f"data: {msg}\n\n")
                        app_logger.info(
                            f"Converted PDF page for session {session_id}: {image_info['saved_name']}"
                        )

                except Exception as e:
                    app_logger.error(f"Error processing PDF {original_filename}: {e}")
                    return (
                        jsonify({"error": f"ไม่สามารถประมวลผลไฟล์ PDF ได้: {str(e)}"}),
                        400,
                    )

            else:
                unique_filename = f"{uuid.uuid4()}.{ext}"
                filepath = os.path.join(session_upload_path, unique_filename)
                
                # บันทึกไฟล์ต้นฉบับ
                file.save(filepath)
                
                # สร้างเวอร์ชันเว็บสำหรับรูปภาพปกติ
                try:
                    with Image.open(filepath) as img:
                        web_filename = f"web_{unique_filename}"
                        web_filepath = os.path.join(session_upload_path, web_filename)
                        web_image_data = create_web_optimized_image(img, max_width=800, quality=60)
                        
                        with open(web_filepath, 'wb') as f:
                            f.write(web_image_data)
                        
                        file_info = {
                            "original_name": original_filename,
                            "saved_name": unique_filename,
                            "web_name": web_filename,
                            "url": f"/uploads/{session_id}/{web_filename}",  # ใช้เวอร์ชันเว็บสำหรับแสดงผล
                            "original_url": f"/uploads/{session_id}/{unique_filename}",  # เก็บ URL ต้นฉบับไว้
                        }
                except Exception as e:
                    app_logger.warning(f"Could not create web version for {unique_filename}: {e}")
                    # ถ้าสร้างเวอร์ชันเว็บไม่ได้ ใช้ต้นฉบับ
                    file_info = {
                        "original_name": original_filename,
                        "saved_name": unique_filename,
                        "url": f"/uploads/{session_id}/{unique_filename}",
                    }
                
                uploaded_files_info.append(file_info)

                msg = json.dumps({"event": "new_image", "data": file_info, "session_id": session_id})
                announcer.announce(msg=f"data: {msg}\n\n")
                app_logger.info(
                    f"Uploaded file for session {session_id}: {unique_filename}"
                )

    return jsonify(
        {"message": "Files uploaded successfully", "files": uploaded_files_info}
    )


# === API จัดการผลลัพธ์และเฉลย (ต้องระบุโหมด) ===
@app.route("/clear_results_single", methods=["POST"])
def clear_results_single():
    session_data = get_session_data()
    if "single_results" in session_data:
        del session_data["single_results"]
        save_session_data(session_data)
    app_logger.info("Single mode results cleared")
    return jsonify({"message": "Results for single mode cleared."})


@app.route("/clear_results_multi", methods=["POST"])
def clear_results_multi():
    session_data = get_session_data()
    if "multi_results" in session_data:
        del session_data["multi_results"]
        save_session_data(session_data)
    app_logger.info("Multi mode results cleared")
    return jsonify({"message": "Results for multi mode cleared."})


@app.route("/get_results_single")
def get_results_single():
    session_data = get_session_data()
    results = session_data.get("single_results", [])
    
    # แยกผลลัพธ์เป็น 2 กลุ่ม
    not_found_group = []  # กลุ่มที่ไม่พบชื่อหรือรหัสอ่านไม่ได้ - ไม่ sort เลย
    found_group = []      # กลุ่มที่พบชื่อและรหัสปกติ - sort ตามรหัส
    
    for result in results:
        student_name = result.get("student_name", "")
        student_id = result.get("student_id", "")
        has_issues = result.get("has_issues", False)  # ตรวจสอบว่ามีปัญหาหรือไม่
        
        # Debug: แสดงข้อมูลจริงที่ได้รับ
        print(f"DEBUG - Student ID: {student_id}, Name: '{student_name}', has_issues: {has_issues}")
        
        # ตรวจสอบว่าพบชื่อและรหัสนักศึกษาหรือไม่
        name_str = str(student_name).strip() if student_name else ""
        is_name_not_found = (
            name_str == "ไม่พบชื่อ" or 
            name_str == "ไม่พบชื่อในรายชื่อ" or 
            name_str == "ข้อผิดพลาด" or
            name_str == "" or
            student_name is None or
            not student_name or
            "ไม่พบ" in name_str
        )
        
        is_id_invalid = (
            student_id == "Error Reading ID" or
            student_id == "ERROR" or
            "-" in str(student_id) or  # รหัสที่อ่านไม่ครบ เช่น "12345-7890"
            not student_id or
            str(student_id).strip() == ""
        )
        
        # ถ้าไม่พบชื่อหรือรหัสอ่านไม่ได้หรือมีปัญหา ให้ใส่ในกลุ่มไม่ sort
        if is_name_not_found or is_id_invalid or has_issues:
            not_found_group.append(result)
            print(f"DEBUG - Added to NOT_FOUND: {student_id} (has_issues: {has_issues})")
        else:
            found_group.append(result)
            print(f"DEBUG - Added to FOUND: {student_id} - '{student_name}'")
    
    # sort เฉพาะกลุ่มที่พบชื่อและรหัสปกติ
    found_group_sorted = sorted(found_group, key=lambda x: str(x.get("student_id", "")).lower())
    
    # รวมผลลัพธ์: กลุ่มไม่พบชื่อ/รหัสอ่านไม่ได้ก่อน (ไม่ sort) + กลุ่มพบชื่อ+รหัสปกติ (sort แล้ว)
    final_results = not_found_group + found_group_sorted
    
    print(f"DEBUG - Final order: NOT_FOUND={len(not_found_group)}, FOUND={len(found_group_sorted)}")
    
    return jsonify({"results": final_results})


@app.route("/get_results_multi")
def get_results_multi():
    session_data = get_session_data()
    results = session_data.get("multi_results", [])
    
    # แยกผลลัพธ์เป็น 2 กลุ่ม
    not_found_group = []  # กลุ่มที่ไม่พบชื่อหรือรหัสอ่านไม่ได้ - ไม่ sort เลย
    found_group = []      # กลุ่มที่พบชื่อและรหัสปกติ - sort ตามรหัส
    
    for result in results:
        student_name = result.get("student_name", "")
        student_id = result.get("student_id", "")
        has_issues = result.get("has_issues", False)  # ตรวจสอบว่ามีปัญหาหรือไม่ (ไม่ใช้ใน multi mode)
        
        # ตรวจสอบว่าพบชื่อและรหัสนักศึกษาหรือไม่
        is_name_not_found = (
            student_name == "ไม่พบชื่อ" or 
            student_name == "ไม่พบชื่อในรายชื่อ" or 
            student_name == "ข้อผิดพลาด" or
            not student_name or 
            student_name.strip() == "" or
            student_name.strip() == "ไม่พบชื่อ"
        )
        
        is_id_invalid = (
            student_id == "Error Reading ID" or
            student_id == "ERROR" or
            "-" in str(student_id) or  # รหัสที่อ่านไม่ครบ เช่น "12345-7890"
            not student_id or
            str(student_id).strip() == ""
        )
        
        # ถ้าไม่พบชื่อหรือรหัสอ่านไม่ได้ ให้ใส่ในกลุ่มไม่ sort (ไม่ตรวจสอบ has_issues ใน multi mode)
        if is_name_not_found or is_id_invalid:
            not_found_group.append(result)
        else:
            found_group.append(result)
    
    # sort เฉพาะกลุ่มที่พบชื่อและรหัสปกติ
    found_group_sorted = sorted(found_group, key=lambda x: str(x.get("student_id", "")).lower())
    
    # รวมผลลัพธ์: กลุ่มไม่พบชื่อ/รหัสอ่านไม่ได้ก่อน (ไม่ sort) + กลุ่มพบชื่อ+รหัสปกติ (sort แล้ว)
    final_results = not_found_group + found_group_sorted
    
    return jsonify({"results": final_results})


@app.route("/view_answer_key_single")
def view_answer_key_single():
    try:
        config_path = get_session_path("config")
        answer_key_path = os.path.join(config_path, "answer_key_single.csv")
        if not os.path.exists(answer_key_path):
            return jsonify({"success": False, "message": "ไม่พบไฟล์เฉลยโหมด single"})

        df = pd.read_csv(answer_key_path, header=None)
        data = [
            {"question": int(row[0]), "answer": int(row[1])} for _, row in df.iterrows()
        ]
        return jsonify({"success": True, "data": data})
    except ValueError:
        return jsonify({"success": False, "message": "No active session"})
    except Exception as e:
        app_logger.error(f"Error reading single mode answer key: {e}")
        return jsonify({"success": False, "message": "เกิดข้อผิดพลาดในการอ่านไฟล์เฉลย"})


@app.route("/view_answer_key_multi")
def view_answer_key_multi():
    try:
        config_path = get_session_path("config")
        answer_key_path = os.path.join(config_path, "answer_key_multi.csv")
        if not os.path.exists(answer_key_path):
            return jsonify({"success": False, "message": "ไม่พบไฟล์เฉลยโหมด multi"})

        df = pd.read_csv(answer_key_path, header=None)
        data = [
            {"question": int(row[0]), "answer": str(row[1])} for _, row in df.iterrows()
        ]
        return jsonify({"success": True, "data": data})
    except ValueError:
        return jsonify({"success": False, "message": "No active session"})
    except Exception as e:
        app_logger.error(f"Error reading multi mode answer key: {e}")
        return jsonify({"success": False, "message": "เกิดข้อผิดพลาดในการอ่านไฟล์เฉลย"})


@app.route('/get_answer_key_single')
def get_answer_key_single():
    try:
        answer_key, err = load_answer_key('single')
        if err:
            return jsonify({
                "has_answer_key": False,
                "filename": None,
                "error": "ยังไม่ได้อัปโหลดไฟล์เฉลย กรุณาอัปโหลดไฟล์เฉลยก่อนใช้งาน"
            }), 404
        serializable_key = {}
        for q_num, answer in answer_key.items():
            if isinstance(answer, set):
                serializable_key[q_num] = list(answer)
            else:
                serializable_key[q_num] = answer
        return jsonify({
            "has_answer_key": True,
            "answer_key": serializable_key,
            "filename": f"answer_key_single.csv"
        })
    except ValueError:
        return jsonify({
            "has_answer_key": False,
            "error": "Session ยังไม่ถูกสร้าง กรุณารีเฟรชหน้าเว็บหรือเริ่มต้น session ก่อน"
        }), 400
    except Exception as e:
        app_logger.error(f"Error getting answer key for single mode: {e}")
        return jsonify({"has_answer_key": False, "error": str(e)}), 500

@app.route('/get_answer_key_multi')
def get_answer_key_multi():
    try:
        answer_key, err = load_answer_key('multi')
        if err:
            return jsonify({
                "has_answer_key": False,
                "filename": None,
                "error": "ยังไม่ได้อัปโหลดไฟล์เฉลย กรุณาอัปโหลดไฟล์เฉลยก่อนใช้งาน"
            }), 404
        serializable_key = {}
        for q_num, answer in answer_key.items():
            if isinstance(answer, set):
                serializable_key[q_num] = list(answer)
            else:
                serializable_key[q_num] = answer
        return jsonify({
            "has_answer_key": True,
            "answer_key": serializable_key,
            "filename": f"answer_key_multi.csv"
        })
    except Exception as e:
        app_logger.error(f"Error getting answer key for multi mode: {e}")
        return jsonify({"has_answer_key": False, "error": str(e)}), 500


@app.route("/download_results_single", methods=["POST"])
def download_results_single():
    data = request.get_json()
    results_data = data.get("results")
    output_filename = data.get("filename", "omr_results_single")

    if not results_data:
        return jsonify({"error": "No results data provided"}), 400

    formatted_data = []
    for item in results_data:
        # ใช้ student_name เป็นหลัก เพราะเป็นข้อมูลที่อัปเดตล่าสุด
        student_name = item.get("student_name", "")
        
        # ถ้า student_name ว่างหรือเป็น "ไม่พบชื่อ" ให้ลองใช้ fname/lname
        if not student_name or student_name in ["ไม่พบชื่อ", "ไม่พบชื่อในรายชื่อ"]:
            fname = item.get("fname", "")
            lname = item.get("lname", "")
            if fname and lname:
                student_name = f"{fname} {lname}".strip()
            elif fname:
                student_name = fname
        
        # แยกชื่อและนามสกุลจาก student_name
        if " " in student_name:
            fname, lname = student_name.split(" ", 1)
        else:
            fname, lname = student_name, ""
            
        formatted_data.append(
            {
                "student_id": item.get("student_id", ""),
                "fname": fname,
                "lname": lname,
                "score": item.get("score", 0),
                "total": item.get("total", 0),
            }
        )

    output_df = pd.DataFrame(formatted_data)
    # เรียงลำดับตาม student_id จากน้อยไปมาก
    try:
        output_df["student_id_sort"] = output_df["student_id"].apply(lambda x: int(str(x).replace("-", "0")) if str(x).isdigit() or str(x).replace("-", "0").isdigit() else 999999999999)
        output_df = output_df.sort_values("student_id_sort")
        output_df = output_df.drop(columns=["student_id_sort"])
    except Exception:
        pass
    csv_buffer = io.StringIO()
    output_df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")

    csv_content = csv_buffer.getvalue()
    mem = io.BytesIO()
    mem.write("\ufeff".encode("utf-8"))
    mem.write(csv_content.encode("utf-8"))
    mem.seek(0)

    app_logger.info(f"Downloaded single mode results as: {output_filename}.csv")
    return send_file(
        mem,
        as_attachment=True,
        download_name=f"{output_filename}.csv",
        mimetype="text/csv; charset=utf-8",
    )


@app.route("/download_results_multi", methods=["POST"])
def download_results_multi():
    data = request.get_json()
    results_data = data.get("results")
    output_filename = data.get("filename", "omr_results_multi")

    if not results_data:
        return jsonify({"error": "No results data provided"}), 400

    formatted_data = []
    for item in results_data:
        # ใช้ student_name เป็นหลัก เพราะเป็นข้อมูลที่อัปเดตล่าสุด
        student_name = item.get("student_name", "")
        
        # ถ้า student_name ว่างหรือเป็น "ไม่พบชื่อ" ให้ลองใช้ fname/lname
        if not student_name or student_name in ["ไม่พบชื่อ", "ไม่พบชื่อในรายชื่อ"]:
            fname = item.get("fname", "")
            lname = item.get("lname", "")
            if fname and lname:
                student_name = f"{fname} {lname}".strip()
            elif fname:
                student_name = fname
        
        # แยกชื่อและนามสกุลจาก student_name
        if " " in student_name:
            fname, lname = student_name.split(" ", 1)
        else:
            fname, lname = student_name, ""
            
        formatted_data.append(
            {
                "student_id": item.get("student_id", ""),
                "fname": fname,
                "lname": lname,
                "score": item.get("score", 0),
                "total": item.get("total", 0),
                "status": item.get("status", ""),
            }
        )

    output_df = pd.DataFrame(formatted_data)
    # เรียงลำดับตาม student_id จากน้อยไปมาก
    try:
        output_df["student_id_sort"] = output_df["student_id"].apply(lambda x: int(str(x).replace("-", "0")) if str(x).isdigit() or str(x).replace("-", "0").isdigit() else 999999999999)
        output_df = output_df.sort_values("student_id_sort")
        output_df = output_df.drop(columns=["student_id_sort"])
    except Exception:
        pass
    csv_buffer = io.StringIO()
    output_df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")

    csv_content = csv_buffer.getvalue()
    mem = io.BytesIO()
    mem.write("\ufeff".encode("utf-8"))
    mem.write(csv_content.encode("utf-8"))
    mem.seek(0)

    app_logger.info(f"Downloaded multi mode results as: {output_filename}.csv")
    return send_file(
        mem,
        as_attachment=True,
        download_name=f"{output_filename}.csv",
        mimetype="text/csv; charset=utf-8",
    )


@app.route("/upload_student_list", methods=["POST"])
def upload_student_list():
    import csv
    import chardet
    try:
        if "student_list" not in request.files:
            return jsonify({"success": False, "message": "ไม่พบไฟล์รายชื่อนักเรียน"}), 400

        file = request.files["student_list"]
        if not file or not file.filename.lower().endswith(".csv"):
            return jsonify({"success": False, "message": "กรุณาเลือกไฟล์ .csv เท่านั้น"}), 400

        config_path = get_session_path("config")
        student_list_path = os.path.join(config_path, "student_list.csv")

        # ตรวจสอบ encoding ก่อนบันทึก
        file_bytes = file.read()
        result = chardet.detect(file_bytes)
        encoding = result['encoding']
        # ถ้า encoding ไม่ใช่ utf-8/utf-8-sig ให้แปลงเป็น utf-8
        if encoding and encoding.lower() not in ["utf-8", "utf-8-sig"]:
            try:
                text = file_bytes.decode(encoding)
                with open(student_list_path, "w", encoding="utf-8") as f:
                    f.write(text)
            except Exception as e:
                app_logger.error(f"Error converting file encoding: {e}")
                return jsonify({"success": False, "message": "เกิดข้อผิดพลาดในการแปลง encoding"}), 500
        else:
            with open(student_list_path, "wb") as f:
                f.write(file_bytes)

        # ตรวจสอบและแปลงไฟล์ให้รองรับหลายรูปแบบ
        students = []
        with open(student_list_path, encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            
            # ตรวจสอบและข้าม header row
            first_row = True
            for row in reader:
                if first_row:
                    first_row = False
                    # ตรวจสอบว่าแถวแรกเป็น header หรือไม่
                    if (len(row) > 0 and 
                        any(keyword in str(row[0]).upper() for keyword in ["STUDENT_CODE", "STUDENT_ID", "รหัส"]) or
                        any(keyword in str(row[1]).upper() if len(row) > 1 else "" for keyword in ["FNAME_TH", "NAME", "ชื่อ"])):
                        app_logger.info(f"Skipping header row: {row}")
                        continue  # ข้าม header row
                if not row or len(row) < 2:  # ข้ามแถวว่างหรือไม่ครบ
                    continue
                    
                row = [col.strip() for col in row]
                student_id = row[0]
                
                if len(row) >= 4:
                    # รูปแบบ: รหัส, ชื่อ, นามสกุล, อื่นๆ
                    fname = row[1]
                    lname = row[2]
                    fullname = fname + " " + lname
                elif len(row) == 3:
                    # รูปแบบ: รหัส, ชื่อ, นามสกุล
                    fname = row[1]
                    lname = row[2]
                    fullname = fname + " " + lname
                elif len(row) == 2:
                    # รูปแบบ: รหัส, ชื่อเต็ม (รูปแบบของไฟล์ปัจจุบัน)
                    fullname = row[1]
                    fname = fullname
                    lname = ""
                else:
                    continue
                    
                students.append({
                    "student_id": student_id.strip(),
                    "name": fullname.strip(),
                    "fname": fname.strip(),
                    "lname": lname.strip()
                })

        # บันทึก students ลง session_data
        session_data = get_session_data()
        session_data["student_list_filename"] = file.filename
        session_data["student_list"] = students  # เพิ่มบรรทัดนี้เพื่อบันทึกรายชื่อ
        save_session_data(session_data)

        app_logger.info(
            f"Student list uploaded for session {session['session_id']}: {file.filename}"
        )
        return jsonify(
            {
                "success": True,
                "message": "บันทึกรายชื่อนักเรียนสำเร็จ",
                "filename": file.filename,
                "count": len(students),
            }
        )
    except ValueError:
        return jsonify({"error": "No active session"}), 400
    except Exception as e:
        app_logger.error(f"Error uploading student list: {e}")
        return jsonify({"success": False, "message": "เกิดข้อผิดพลาดในการบันทึกไฟล์"}), 500


@app.route("/view_student_list")
def view_student_list():
    import csv
    try:
        config_path = get_session_path("config")
        student_list_path = os.path.join(config_path, "student_list.csv")
        if not os.path.exists(student_list_path):
            return jsonify({"success": False, "message": "ไม่พบไฟล์รายชื่อนักศึกษา"})

        students = []
        with open(student_list_path, encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader, None)  # ข้าม header
            for row in reader:
                row = [col.strip() for col in row]
                if len(row) >= 4:
                    student_id = row[0]
                    fname = row[1]
                    lname = row[2]
                    fullname = fname + " " + lname
                elif len(row) == 3:
                    student_id = row[0]
                    fname = row[1]
                    lname = ""
                    fullname = fname
                elif len(row) == 2:
                    student_id = row[0]
                    fname = row[1]
                    lname = ""
                    fullname = fname
                else:
                    continue
                students.append({"student_id": student_id, "name": fullname, "fname": fname, "lname": lname})
        return jsonify({"success": True, "data": students})
    except ValueError:
        return jsonify({"success": False, "message": "No active session"})
    except Exception as e:
        app_logger.error(f"Error reading student list: {e}")
        return jsonify(
            {"success": False, "message": "เกิดข้อผิดพลาดในการอ่านไฟล์รายชื่อนักศึกษา"}
        )


@app.route("/delete_images", methods=["POST"])
def delete_images():
    data = request.get_json()
    filenames = data.get("filenames", [])
    deleted_count = 0

    try:
        session_upload_path = get_session_path("uploads")
    except ValueError:
        return jsonify({"error": "No active session"}), 400

    for filename in filenames:
        filepath = os.path.join(session_upload_path, filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                deleted_count += 1
                app_logger.info(
                    f"Deleted file for session {session['session_id']}: {filename}"
                )
            except Exception as e:
                app_logger.error(f"Error deleting {filepath}: {e}")

    msg = json.dumps({"event": "delete_images", "data": filenames})
    announcer.announce(msg=f"data: {msg}\n\n")

    return jsonify({"message": f"Deleted {deleted_count} files."})


@app.route("/get_student_detailed_answers")
def get_student_detailed_answers():
    """ดึงคำตอบรายละเอียดของนักศึกษาสำหรับการแก้ไขคะแนน"""
    student_id = request.args.get("student_id")
    mode = request.args.get("mode", "single")

    if not student_id:
        return jsonify({"success": False, "error": "Missing student_id"})

    try:
        session_data = get_session_data()
        detailed_key = f"{mode}_detailed_answers"

        if detailed_key in session_data and student_id in session_data[detailed_key]:
            student_answers_raw = session_data[detailed_key][student_id]
            # Ensure all 'answers' are lists for JSON
            student_answers_clean = {}
            for q, data in student_answers_raw.items():
                ans = data.get("answers", [])
                student_answers_clean[q] = {
                    "answers": list(ans) if isinstance(ans, set) else ans,
                    "status": data.get("status", "incorrect"),
                }
            return jsonify({"success": True, "answers": student_answers_clean})
        else:
            return jsonify(
                {
                    "success": False,
                    "error": f"No detailed answers found for student {student_id} in {mode} mode",
                }
            )
    except Exception as e:
        app_logger.error(f"Error getting student detailed answers: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route("/download_template")
def download_template():
    return send_from_directory(
        os.path.join("static", "assets"), "answer_sheet.pdf", as_attachment=True
    )


@app.route("/check_pdf_support", methods=["GET"])
def check_pdf_support():
    return jsonify(
        {
            "pdf_supported": True,
            "message": (
                "PDF conversion is supported"
            ),
        }
    )



def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS




@app.route("/clean_images", methods=["POST"])
def clean_images():
    data = request.get_json()
    filenames = data.get("filenames", [])
    cleaned_count = 0
    cleaned_files = []

    try:
        session_upload_path = get_session_path("uploads")
    except ValueError:
        return jsonify({"error": "No active session"}), 400

    for filename in filenames:
        filepath = os.path.join(session_upload_path, filename)
        if os.path.exists(filepath):
            if clean_image_file(filepath):
                cleaned_count += 1
                cleaned_files.append(filename)

    if cleaned_count > 0:
        msg_data = {
            "event": "images_cleaned",
            "data": {"filenames": cleaned_files, "timestamp": int(time.time())},
        }
        announcer.announce(msg=f"data: {json.dumps(msg_data)}\n\n")

    return jsonify({"message": f"Cleaned {cleaned_count} images."})


@app.route("/optimize_images", methods=["POST"])
def optimize_images():
    """สร้างเวอร์ชันเว็บสำหรับรูปภาพที่มีอยู่แล้ว"""
    try:
        session_upload_path = get_session_path("uploads")
    except ValueError:
        return jsonify({"error": "No active session"}), 400

    image_files = [
        f for f in os.listdir(session_upload_path) 
        if allowed_file(f) and not f.startswith("web_")
    ]

    if not image_files:
        return jsonify({"message": "No images to optimize."}), 200

    optimized_count = 0
    for filename in image_files:
        filepath = os.path.join(session_upload_path, filename)
        web_filename = f"web_{filename}"
        web_filepath = os.path.join(session_upload_path, web_filename)
        
        # ถ้ามีเวอร์ชันเว็บอยู่แล้ว ข้าม
        if os.path.exists(web_filepath):
            continue
            
        try:
            with Image.open(filepath) as img:
                web_image_data = create_web_optimized_image(img, max_width=800, quality=60)
                with open(web_filepath, 'wb') as f:
                    f.write(web_image_data)
                optimized_count += 1
                
                # ส่งข้อมูลผ่าน SSE
                msg_data = {
                    "event": "image_optimized",
                    "filename": filename,
                    "web_filename": web_filename,
                    "optimized_count": optimized_count,
                    "total_count": len(image_files),
                }
                announcer.announce(msg=f"data: {json.dumps(msg_data)}\n\n")
                
        except Exception as e:
            app_logger.error(f"Error optimizing {filename}: {e}")

    return jsonify({"message": f"Optimized {optimized_count} images for web display."})


@app.route("/get_student_list")
def get_student_list():
    try:
        config_path = get_session_path("config")
        student_list_path = os.path.join(config_path, "student_list.csv")
        if os.path.exists(student_list_path):
            session_data = get_session_data()
            return jsonify(
                {
                    "has_student_list": True,
                    "filename": session_data.get(
                        "student_list_filename", "student_list.csv"
                    ),
                }
            )
    except ValueError:
        return jsonify(
            {"has_student_list": False, "filename": None}
        )  # No session is not an error here
    return jsonify({"has_student_list": False, "filename": None})


@app.route("/uploads/<session_id>/<filename>")
def uploaded_file(session_id, filename):
    session_upload_path = os.path.join(app.config["UPLOAD_FOLDER"], session_id)
    return send_from_directory(session_upload_path, filename)


@app.route("/debug_output/<session_id>/<filename>")
def debug_file(session_id, filename):
    session_debug_path = os.path.join(DEBUG_FOLDER, session_id)
    return send_from_directory(session_debug_path, filename)


# === Session Management APIs ===
@app.route("/get_session_info")
def get_session_info():
    if "session_id" not in session:
        return jsonify({"has_session": False})

    # <-- FIX 3: อ่านจาก Global list เพื่อความถูกต้อง
    global_sessions = get_global_session_list()
    active_sessions = global_sessions.get("active_sessions", {})

    if session["session_id"] in active_sessions:
        active_sessions[session["session_id"]][
            "last_activity"
        ] = datetime.now().isoformat()
        save_global_session_list(global_sessions)

    return jsonify(
        {
            "has_session": True,
            "session_id": session["session_id"][:8] + "...",
            "session_id_full": session["session_id"],
            "device_type": session.get("device_type", "unknown"),
            "connected_devices": len(active_sessions),
        }
    )


@app.route("/generate_mobile_link")
def generate_mobile_link():
    """สร้างลิงก์สำหรับมือถือ"""
    if "session_id" not in session:
        return jsonify({
            "success": False,
            "error": "Session ยังไม่ถูกสร้าง กรุณารีเฟรชหน้าเว็บหรือเริ่มต้น session ก่อน"
        }), 400

    # ใช้ dynamic base URL
    base_url = get_base_url(request)
    mobile_link = f"{base_url}/?session_id={session['session_id']}"

    return jsonify({"mobile_link": mobile_link, "session_id": session["session_id"], "base_url": base_url})


@app.route("/generate_qr_code")
def generate_qr_code():
    """สร้าง QR Code สำหรับมือถือ (ใช้ API แทน library)"""
    if "session_id" not in session:
        return jsonify({"error": "No active session"}), 400

    # ใช้ dynamic base URL
    base_url = get_base_url(request)
    mobile_link = f"{base_url}/?session_id={session['session_id']}"

    # ใช้ QR Server API (ไม่ต้องติดตั้งอะไร)
    qr_api_url = (
        f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={mobile_link}"
    )

    return jsonify(
        {
            "mobile_link": mobile_link,
            "qr_code_url": qr_api_url,
            "session_id": session["session_id"],
            "base_url": base_url,
        }
    )


@app.route("/clear_session", methods=["POST"])
def clear_session():
    try:
        # ล้างข้อมูลในโฟลเดอร์ uploads, debug_output, config ของ session ปัจจุบัน
        for folder_type in ["uploads", "debug_output", "config"]:
            folder_path = get_session_path(folder_type)
            clear_folder(folder_path)
        app_logger.info(f"Cleared data for session: {session.get('session_id')}")
        return jsonify({"success": True, "message": "Session data cleared, session_id preserved."})
    except Exception as e:
        app_logger.error(f"Error clearing session data: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


@app.errorhandler(404)
def not_found_error(error):
    if not request.path.endswith("favicon.ico"):
        app_logger.warning(
            f"404 Error: {request.method} {request.url} not found from {request.remote_addr}"
        )

    if request.path.startswith("/api/") or request.is_json:
        return jsonify({"error": "Endpoint not found"}), 404

    if request.path.startswith("/static/") or request.path.startswith("/uploads/"):
        return jsonify({"error": "File not found"}), 404

    return render_template("index.html"), 404

# ...existing code...

@app.route("/download_answer_key_single")
def download_answer_key_single():
    try:
        config_path = get_session_path("config")
        answer_key_path = os.path.join(config_path, "answer_key_single.csv")
        if not os.path.exists(answer_key_path):
            return jsonify({"error": "ไม่พบไฟล์เฉลยโหมด single"}), 404
        return send_file(answer_key_path, as_attachment=True, download_name="answer_key_single.csv")
    except Exception as e:
        app_logger.error(f"Error downloading answer key single: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/download_answer_key_multi")
def download_answer_key_multi():
    try:
        config_path = get_session_path("config")
        answer_key_path = os.path.join(config_path, "answer_key_multi.csv")
        if not os.path.exists(answer_key_path):
            return jsonify({"error": "ไม่พบไฟล์เฉลยโหมด multi"}), 404
        return send_file(answer_key_path, as_attachment=True, download_name="answer_key_multi.csv")
    except Exception as e:
        app_logger.error(f"Error downloading answer key multi: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/download_student_list")
def download_student_list():
    try:
        config_path = get_session_path("config")
        student_list_path = os.path.join(config_path, "student_list.csv")
        if not os.path.exists(student_list_path):
            return jsonify({"error": "ไม่พบไฟล์รายชื่อนักศึกษา"}), 404
        import pandas as pd
        df = pd.read_csv(student_list_path, encoding="utf-8-sig")
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
        csv_content = csv_buffer.getvalue()
        mem = io.BytesIO()
        mem.write("\ufeff".encode("utf-8"))
        mem.write(csv_content.encode("utf-8"))
        mem.seek(0)
        return send_file(
            mem,
            as_attachment=True,
            download_name="student_list.csv",
            mimetype="text/csv; charset=utf-8",
        )
    except Exception as e:
        app_logger.error(f"Error downloading student list: {e}")
        return jsonify({"error": str(e)}), 500

# ...existing code...
@app.route("/get_download_status")
def get_download_status():
    try:
        config_path = get_session_path("config")
        has_answer_key_single = os.path.exists(os.path.join(config_path, "answer_key_single.csv"))
        has_answer_key_multi = os.path.exists(os.path.join(config_path, "answer_key_multi.csv"))
        has_student_list = os.path.exists(os.path.join(config_path, "student_list.csv"))
        return jsonify({
            "has_answer_key_single": has_answer_key_single,
            "has_answer_key_multi": has_answer_key_multi,
            "has_student_list": has_student_list
        })
    except Exception:
        return jsonify({
            "has_answer_key_single": False,
            "has_answer_key_multi": False,
            "has_student_list": False
        })
# ...existing code...

@app.route("/get_student_name_by_id", methods=["POST"])
def get_student_name_by_id():
    """ค้นหาชื่อนักศึกษาจากรหัส"""
    try:
        data = request.get_json()
        student_id = data.get("student_id")
        
        if not student_id:
            return jsonify({"success": False, "error": "Missing student_id"}), 400
            
        session_data = get_session_data()
        student_list = session_data.get("student_list", [])
        
        # ค้นหานักศึกษาในรายชื่อ
        for student in student_list:
            if str(student.get("student_id", "")).strip() == str(student_id).strip():
                return jsonify({
                    "success": True,
                    "student_name": student.get("name", ""),
                    "student_id": student_id
                })
        
        return jsonify({"success": False, "error": "Student not found"})
        
    except Exception as e:
        app_logger.error(f"Error getting student name: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/get_available_students", methods=["POST"])
def get_available_students():
    """ดึงรายชื่อนักศึกษาที่ยังไม่ได้ใช้งาน"""
    try:
        data = request.get_json()
        mode = data.get("mode", "single")
        current_student_id = data.get("current_student_id")  # รหัสนักศึกษาปัจจุบันที่กำลังแก้ไข
        
        app_logger.info(f"get_available_students called with mode: {mode}, current_student_id: {current_student_id}")
        
        session_data = get_session_data()
        student_list = session_data.get("student_list", [])
        
        if not student_list:
            return jsonify({"success": False, "error": "No student list found"})
        
        # ดึงรายชื่อที่ใช้งานแล้วจากผลลัพธ์
        results_key = f"{mode}_results"
        used_student_ids = set()
        
        if results_key in session_data:
            for result in session_data[results_key]:
                student_id = str(result.get("student_id", "")).strip()
                if student_id and student_id != "ERROR" and student_id != "-":
                    used_student_ids.add(student_id)
        
        app_logger.info(f"Found {len(used_student_ids)} used student IDs: {list(used_student_ids)}")
        
        # ถ้ากำลังแก้ไขนักศึกษาคนใดคนหนึ่ง ให้ไม่นับรหัสเดิมของเขาเป็นที่ใช้งานแล้ว
        if current_student_id:
            used_student_ids.discard(str(current_student_id).strip())
            app_logger.info(f"Removed current student {current_student_id} from used list. Remaining: {list(used_student_ids)}")
        
        # สร้างรายชื่อที่ยังไม่ได้ใช้งาน (ข้าม header row)
        available_students = []
        for i, student in enumerate(student_list):
            # ข้ามแถวแรกที่เป็น header
            if i == 0:
                # ตรวจสอบว่าแถวแรกเป็น header หรือไม่
                student_id_value = str(student.get("student_id", "")).strip().lower()
                name_value = str(student.get("name", "")).strip().lower()
                
                # รายการคำที่บ่งบอกว่าเป็น header
                header_keywords_id = [
                    "student_id", "student_code", "รหัสนักศึกษา", "รหัส", "id", "รหัสประจำตัว",
                    "code", "std_code", "student_no"
                ]
                header_keywords_name = [
                    "name", "ชื่อ", "student_name", "ชื่อนักศึกษา", "ชื่อ-สกุล", "ชื่อสกุล",
                    "fname_th", "std_lname_th", "firstname", "lastname", "fullname"
                ]
                
                # ตรวจสอบทั้งค่าตรงและค่าที่มีคำสำคัญ
                is_header = (
                    student_id_value in header_keywords_id or 
                    name_value in header_keywords_name or
                    any(keyword in student_id_value for keyword in ["student_code", "student_id", "code"]) or
                    any(keyword in name_value for keyword in ["fname_th", "std_lname_th", "name"])
                )
                
                if is_header:
                    app_logger.info(f"Skipping header row: student_id='{student_id_value}', name='{name_value}'")
                    continue  # ข้าม header row
            
            student_id = str(student.get("student_id", "")).strip()
            student_name = str(student.get("name", "")).strip()
            
            # ตรวจสอบว่าเป็นข้อมูลที่ถูกต้อง (ไม่ใช่ header หรือข้อมูลเปล่า)
            header_keywords = [
                "student_id", "student_code", "รหัสนักศึกษา", "รหัส", "id", 
                "fname_th", "std_lname_th", "name", "ชื่อ", "code"
            ]
            
            # ตรวจสอบว่าไม่ใช่ header และไม่ใช่ข้อมูลเปล่า
            is_valid_student = (
                student_id and student_name and 
                student_id not in used_student_ids and
                student_id.lower() not in header_keywords and
                student_name.lower() not in header_keywords and
                not any(keyword in student_id.lower() for keyword in ["student_code", "student_id", "fname_th", "std_lname_th"]) and
                not any(keyword in student_name.lower() for keyword in ["student_code", "student_id", "fname_th", "std_lname_th"]) and
                len(student_id) > 3  # รหัสนักศึกษาต้องมีความยาวมากกว่า 3 ตัวอักษร
            )
            
            if is_valid_student:
                available_students.append({
                    "student_id": student_id,
                    "name": student_name,
                    "display_text": f"{student_id} - {student_name}"
                })
        
        # เรียงตามรหัสนักศึกษา
        available_students.sort(key=lambda x: x["student_id"])
        
        app_logger.info(f"Returning {len(available_students)} available students out of {len(student_list)} total")
        
        return jsonify({
            "success": True,
            "students": available_students,
            "total_students": len(student_list),
            "used_count": len(used_student_ids),
            "available_count": len(available_students)
        })
        
    except Exception as e:
        app_logger.error(f"Error getting available students: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/update_student_score", methods=["POST"])

def update_student_score():
    """อัพเดตคะแนนของนักศึกษา"""
    try:
        data = request.get_json()
        student_id = data.get("student_id")
        student_name = data.get("student_name")
        mode = data.get("mode")
        original_student_id = data.get("original_student_id")
        # Front-end sends the entire answer object
        answers_from_fe = data.get("answers")

        if not student_id or not mode or not answers_from_fe:
            return jsonify({"success": False, "error": "Missing required data"}), 400
            
        app_logger.info(f"Received update request - student_id: {student_id}, original_id: {original_student_id}, mode: {mode}")

        # โหลด answer key
        answer_key, err = load_answer_key(mode)
        if err:
            return jsonify({"success": False, "error": err}), 400

        # คำนวณคะแนนใหม่และอัปเดตสถานะ
        new_score = 0
        total_questions = len(answer_key)
        updated_answers_for_storage = {}
        multiple_answers_count = 0  # นับจำนวนข้อที่กาหลายคำตอบ

        for q_num_str, student_data in answers_from_fe.items():
            q_num = int(q_num_str)
            student_answers = set(student_data.get("answers", []))
            has_multiple_answers = len(student_answers) > 1  # ตรวจสอบว่ามีการกาหลายคำตอบหรือไม่

            correct_answer = answer_key.get(q_num)
            status = "incorrect"

            if correct_answer is not None:
                if mode == "single":
                    if (
                        len(student_answers) == 1
                        and list(student_answers)[0] == correct_answer
                    ):
                        status = "correct"
                    elif has_multiple_answers:
                        status = "multiple_answers"
                        multiple_answers_count += 1
                else:  # multi mode
                    correct_set = set(correct_answer)
                    if student_answers == correct_set:
                        status = "correct"
                    elif student_answers and student_answers.issubset(correct_set):
                        status = "partial"

            if status == "correct":
                new_score += 1

            updated_answers_for_storage[q_num] = {
                "answers": list(student_answers),
                "status": status,
                "has_multiple_answers": has_multiple_answers,
            }

        # บันทึกข้อมูลลง session
        session_data = get_session_data()

        # อัพเดตข้อมูลคำตอบรายละเอียด
        detailed_answers_key = f"{mode}_detailed_answers"
        if detailed_answers_key not in session_data:
            session_data[detailed_answers_key] = {}
        session_data[detailed_answers_key][student_id] = updated_answers_for_storage
        
        app_logger.info(f"Updating score for student_id: {student_id}, student_name: {student_name}")

        # อัพเดตคะแนนในผลลัพธ์หลัก
        results_key = f"{mode}_results"
        student_found = False
        if results_key in session_data:
            for i, result in enumerate(session_data[results_key]):
                # ค้นหาด้วย student_id เดิมหรือใหม่
                current_id = str(result.get("student_id", ""))
                if (current_id == str(student_id) or 
                    (original_student_id and current_id == str(original_student_id))):
                    
                    if not original_student_id:
                        original_student_id = result.get("student_id")  # เก็บค่าเดิมไว้
                    
                    # อัพเดตรหัสนักศึกษา
                    session_data[results_key][i]["student_id"] = student_id  # อัพเดทเป็นค่าใหม่
                    if student_name and student_name != 'ไม่พบชื่อในรายชื่อ':
                        session_data[results_key][i]["student_name"] = student_name
                    session_data[results_key][i]["score"] = new_score
                    session_data[results_key][i]["total"] = total_questions
                    
                    # ตรวจสอบและอัพเดตสถานะ is_duplicate
                    # 1. ตรวจสอบว่ารหัสใหม่ซ้ำกับรหัสอื่นหรือไม่
                    new_id_is_duplicate = False
                    for other_result in session_data[results_key]:
                        if (str(other_result.get("student_id", "")) == str(student_id) and 
                            other_result.get("student_file") != result.get("student_file")):
                            new_id_is_duplicate = True
                            # ตั้งแฟล็กรหัสซ้ำให้กระดาษที่มีรหัสเดียวกันด้วย
                            other_result["is_duplicate"] = True
                            break
                    
                    # 2. ตรวจสอบว่ารหัสเดิมยังมีกระดาษอื่นที่ซ้ำกันหรือไม่
                    old_id_count = 0
                    old_id_papers = []
                    if original_student_id and str(original_student_id) != str(student_id):
                        for j, other_result in enumerate(session_data[results_key]):
                            if str(other_result.get("student_id", "")) == str(original_student_id):
                                old_id_count += 1
                                old_id_papers.append(j)
                        
                        # ถ้ารหัสเดิมเหลือแค่ 1 ใบ ให้เปลี่ยน is_duplicate = false
                        if old_id_count == 1:
                            session_data[results_key][old_id_papers[0]]["is_duplicate"] = False
                            app_logger.info(f"Removed duplicate flag from student ID {original_student_id} (only 1 paper left)")
                    
                    # 3. ตั้งค่า is_duplicate สำหรับกระดาษที่แก้ไข
                    session_data[results_key][i]["is_duplicate"] = new_id_is_duplicate
                    
                    # อัพเดตข้อมูลการกาหลายคำตอบและ has_issues
                    if mode == "single":
                        session_data[results_key][i]["multiple_answers_count"] = multiple_answers_count
                        session_data[results_key][i]["has_issues"] = multiple_answers_count > 0 or new_id_is_duplicate
                    else:  # multi mode
                        session_data[results_key][i]["has_issues"] = new_id_is_duplicate
                    
                    student_found = True
                    app_logger.info(f"Updated student at index {i}: {session_data[results_key][i]}")
                    app_logger.info(f"Duplicate status - Old ID: {original_student_id} (count: {old_id_count}), New ID: {student_id} (is_duplicate: {new_id_is_duplicate})")
                    break
            
            if not student_found:
                app_logger.warning(f"Student with ID {student_id} (original: {original_student_id}) not found in results")
                # แสดงรายการ student_id ทั้งหมดเพื่อ debug
                all_ids = [str(r.get("student_id", "")) for r in session_data[results_key]]
                app_logger.info(f"Available student IDs: {all_ids}")

        save_session_data(session_data)

        return jsonify(
            {
                "success": True,
                "new_score": new_score,
                "total": total_questions,
                "original_student_id": original_student_id,
                "message": "Score updated successfully",
            }
        )

    except Exception as e:
        app_logger.error(
            f"Error updating student score: {e} | {traceback.format_exc()}"
        )
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/get_server_info")
def get_server_info():
    """ดึงข้อมูลเซิร์ฟเวอร์ปัจจุบัน"""
    try:
        local_ip = get_local_ip()
        base_url = get_base_url(request)
        
        return jsonify({
            "success": True,
            "local_ip": local_ip,
            "base_url": base_url,
            "port": request.environ.get('SERVER_PORT', '5000'),
            "host": request.host
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


if __name__ == "__main__":
    app_logger.info("Starting OMR System...")
    
    # แสดงข้อมูล IP address
    local_ip = get_local_ip()
    app_logger.info(f"Local IP Address: {local_ip}")
    app_logger.info(f"Server will be accessible at: http://{local_ip}:5000")
    
    # Start cleanup thread once
    if not CLEANUP_THREAD_STARTED:
        t = threading.Thread(target=_cleanup_inactive_sessions_loop, daemon=True)
        t.start()
        CLEANUP_THREAD_STARTED = True
    
    # อ่านค่าจาก environment variables
    host = os.environ.get('SERVER_HOST', '0.0.0.0')
    port = int(os.environ.get('SERVER_PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    app_logger.info(f"Starting server on {host}:{port}")
    app_logger.info(f"Access URLs:")
    app_logger.info(f"  Local:   http://localhost:{port}")
    app_logger.info(f"  Network: http://{local_ip}:{port}")
    
    app.run(debug=debug, host=host, port=port, threaded=True)
