import cv2
import numpy as np
import pandas as pd
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
from imutils import contours
from imutils.perspective import four_point_transform
import io
import os
import traceback
import uuid
import json
import time
from queue import Queue
import logging
from werkzeug.serving import WSGIRequestHandler
import ssl
from datetime import datetime
from pdf2image import convert_from_bytes
from PIL import Image
import secrets
import shutil
import socket
import socket


# --- ปรับปรุงระบบ Logging ---
def setup_logging(app_instance):
    # สร้าง Custom Request Handler ที่กรองข้อมูล SSL และ garbage
    class SilentRequestHandler(WSGIRequestHandler):
        def log_request(self, code="-", size="-"):
            # กรองคำขอที่เป็น SSL/binary garbage
            if (
                hasattr(self, "requestline")
                and self.requestline
                and (
                    not self.requestline.startswith(
                        ("GET ", "POST ", "PUT ", "DELETE ", "HEAD ", "OPTIONS ")
                    )
                    or len(self.requestline) > 1000
                    or any(
                        ord(c) > 127 or ord(c) < 32
                        for c in self.requestline
                        if c not in "\r\n"
                    )
                )
            ):
                return  # ไม่ log คำขอที่เป็น binary/garbage

            # Log เฉพาะคำขอที่ปกติ
            super().log_request(code, size)

        def log_error(self, format, *args):
            # กรองข้อผิดพลาดที่เกี่ยวกับ SSL และ bad request
            if args:
                message = format % args
                # ข้อความที่ไม่ต้องการ log
                filtered_messages = [
                    "Bad request version",
                    "Bad request syntax",
                    "code 400",
                    "Bad HTTP/0.9 request type",
                    "Address already in use",
                    "Connection aborted",
                    "SSL",
                    "handshake",
                ]

                if any(
                    filtered_msg.lower() in message.lower()
                    for filtered_msg in filtered_messages
                ):
                    return  # ไม่ log ข้อผิดพลาดเหล่านี้

            super().log_error(format, *args)

    # ตั้งค่า Flask request handler
    # เก็บ original wsgi_app
    original_wsgi_app = app_instance.wsgi_app

    # สร้าง wrapper function ที่ใช้ SilentRequestHandler
    def wsgi_wrapper(environ, start_response):
        return original_wsgi_app(environ, start_response)

    app_instance.wsgi_app = wsgi_wrapper

    # กรอง Werkzeug logger
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(logging.WARNING)  # เปลี่ยนจาก INFO เป็น WARNING

    # สร้าง custom filter สำหรับ werkzeug
    class CleanLogFilter(logging.Filter):
        def filter(self, record):
            message = record.getMessage().lower()
            # กรองข้อความที่ไม่ต้องการ
            unwanted_patterns = [
                "bad request version",
                "bad request syntax",
                "bad http/0.9 request type",
                "code 400",
                "connection broken",
                "connection aborted",
                "ssl",
                "handshake",
                "certificate",
                "tls",
            ]

            # ตรวจสอบว่ามี pattern ที่ไม่ต้องการหรือไม่
            if any(pattern in message for pattern in unwanted_patterns):
                return False

            # กรองข้อความที่มี binary characters
            if any(
                ord(c) > 127 or (ord(c) < 32 and c not in "\n\r\t")
                for c in record.getMessage()
            ):
                return False

            return True

    # เพิ่ม filter ให้กับ werkzeug logger
    if not any(isinstance(f, CleanLogFilter) for f in werkzeug_logger.filters):
        werkzeug_logger.addFilter(CleanLogFilter())

    # ตั้งค่า root logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

    # สร้าง application logger ที่แยกต่างหาก
    app_logger = logging.getLogger("omr_app")
    app_logger.setLevel(logging.INFO)

    return app_logger


# --- โฟลเดอร์สำหรับเก็บไฟล์ ---
UPLOAD_FOLDER = "uploads"
DEBUG_FOLDER = "debug_output"
STATIC_FOLDER = "config"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}

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


# === Helper Functions for Dynamic Base URL ===
def get_local_ip():
    """ตรวจจับ IP address ของเครื่องในเครือข่าย local"""
    # วิธีที่ 1: ดึงจาก environment variable OMR_BASE_URL ก่อน
    env_base_url = os.environ.get('OMR_BASE_URL')
    if env_base_url:
        try:
            # แยก IP จาก URL เช่น http://172.16.19.35:5000 -> 172.16.19.35
            from urllib.parse import urlparse
            parsed = urlparse(env_base_url)
            if parsed.hostname:
                return parsed.hostname
        except Exception:
            pass
    
    try:
        # วิธีที่ 2: เชื่อมต่อไปยัง Google DNS เพื่อหา IP ที่ใช้งานจริง
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            return local_ip
    except Exception:
        try:
            # วิธีที่ 3: ใช้ hostname
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            if local_ip.startswith("127."):
                # ถ้าได้ localhost ให้ลองวิธีอื่น
                return get_network_ip()
            return local_ip
        except Exception:
            # วิธีที่ 4: fallback เป็น localhost
            return "127.0.0.1"


def get_network_ip():
    """หา IP address ที่ไม่ใช่ localhost"""
    try:
        import netifaces
        # ถ้ามี netifaces ให้ใช้
        for interface in netifaces.interfaces():
            addresses = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addresses:
                for addr in addresses[netifaces.AF_INET]:
                    ip = addr['addr']
                    if not ip.startswith('127.') and not ip.startswith('169.254.'):
                        return ip
    except ImportError:
        # ถ้าไม่มี netifaces ให้ใช้วิธีอื่น
        pass
    
    try:
        # ใช้ socket เพื่อหา IP ที่ active
        import subprocess
        import platform
        
        if platform.system() == "Windows":
            result = subprocess.run(['ipconfig'], capture_output=True, text=True)
            lines = result.stdout.split('\n')
            for line in lines:
                if 'IPv4' in line and '192.168.' in line:
                    ip = line.split(':')[-1].strip()
                    return ip
        else:
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
            ips = result.stdout.strip().split()
            for ip in ips:
                if ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
                    return ip
    except Exception:
        pass
    
    return "127.0.0.1"


def get_base_url(request_obj=None, port=5000):
    """สร้าง base URL ที่ยืดหยุ่นตาม environment"""
    
    # ตรวจสอบว่ามี environment variable สำหรับ base URL หรือไม่
    env_base_url = os.environ.get('OMR_BASE_URL')
    if env_base_url:
        return env_base_url.rstrip('/')
    
    # ตรวจสอบว่ามี ngrok หรือ tunnel service หรือไม่
    ngrok_url = os.environ.get('NGROK_URL')
    if ngrok_url:
        return ngrok_url.rstrip('/')
    
    # ถ้ามี request object ให้ใช้ host จาก request
    if request_obj:
        scheme = 'https' if request_obj.is_secure else 'http'
        host = request_obj.host
        return f"{scheme}://{host}"
    
    # ใช้ local IP address
    local_ip = get_local_ip()
    
    # ตรวจสอบว่าเป็น localhost หรือไม่
    if local_ip == "127.0.0.1":
        return f"http://localhost:{port}"
    else:
        return f"http://{local_ip}:{port}"


class OMRSystemFinal:
    def __init__(self):
        # ปิด debug mode เพื่อเพิ่มความเร็วในการประมวลผล
        self.debug_mode = False  # เปลี่ยนจาก True เป็น False
        self.debug_folder = "debug_output"
        if not os.path.exists(self.debug_folder):
            os.makedirs(self.debug_folder)

    def find_main_blocks(self, contours_list, image_shape):
        h_img, w_img = image_shape[:2]
        image_area = h_img * w_img
        student_id_block_contour = None
        answer_column_contours = []

        for c in contours_list:
            (x, y, w, h) = cv2.boundingRect(c)

            try:
                aspect_ratio = w / float(h)
            except ZeroDivisionError:
                continue

            area_ratio = cv2.contourArea(c) / image_area

            if (
                0.8 < aspect_ratio < 3.0
                and 0.01 < area_ratio < 0.15
                and y < h_img * 0.3
            ):
                if student_id_block_contour is None or cv2.contourArea(
                    c
                ) > cv2.contourArea(student_id_block_contour):
                    student_id_block_contour = c
                    continue

            if (
                0.05 < aspect_ratio < 0.6
                and h > h_img * 0.5
                and 0.008 < area_ratio < 0.15
            ):
                answer_column_contours.append(c)

        return student_id_block_contour, answer_column_contours

    def detect_grid_lines(self, binary_image):
        h, w = binary_image.shape

        # ปรับขนาด kernel ให้เหมาะสมกับขนาดรูป
        h_kernel_size = max(1, min(w // 20, 50))  # จำกัดขนาดสูงสุด
        v_kernel_size = max(1, min(h // 20, 50))  # จำกัดขนาดสูงสุด

        horizontal_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (h_kernel_size, 1)
        )
        horizontal_lines = cv2.erode(binary_image, horizontal_kernel, iterations=1)

        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_size))
        vertical_lines = cv2.erode(binary_image, vertical_kernel, iterations=1)

        h_lines = self._extract_line_positions(horizontal_lines, axis=0)
        v_lines = self._extract_line_positions(vertical_lines, axis=1)

        return h_lines, v_lines

    def _extract_line_positions(self, line_image, axis):
        projection = np.sum(line_image, axis=1 if axis == 0 else 0)
        if projection.max() == 0:
            return []

        threshold = projection.max() * 0.1
        peaks = np.where(projection > threshold)[0]
        if len(peaks) == 0:
            return []

        grouped_peaks, current_group = [], [peaks[0]]
        group_distance = 5
        for peak in peaks[1:]:
            if peak - current_group[-1] <= group_distance:
                current_group.append(peak)
            else:
                grouped_peaks.append(int(np.median(current_group)))
                current_group = [peak]
        grouped_peaks.append(int(np.median(current_group)))

        return sorted(grouped_peaks)

    def create_grid_from_lines(self, h_lines, v_lines, num_questions, num_choices):
        if len(h_lines) < num_questions + 3 or len(v_lines) < num_choices + 2:
            app_logger.warning(
                f"Answer Grid Line Detection Failed: Found {len(h_lines)} h_lines and {len(v_lines)} v_lines. Required h>={num_questions+3}, v>={num_choices+2}."
            )
            return None

        answer_boxes = []
        answer_area_h_lines = h_lines[3:]
        answer_area_v_lines = v_lines[1:]

        if (
            len(answer_area_h_lines) <= num_questions
            or len(answer_area_v_lines) <= num_choices
        ):
            app_logger.warning(
                f"Answer Grid Slicing Failed: Got {len(answer_area_h_lines)} answer_h_lines and {len(answer_area_v_lines)} answer_v_lines. Required h>{num_questions}, v>{num_choices}."
            )
            return None

        for i in range(num_questions):
            row_boxes = []
            for j in range(num_choices):
                if (i + 1) < len(answer_area_h_lines) and (j + 1) < len(
                    answer_area_v_lines
                ):
                    y1, y2 = answer_area_h_lines[i], answer_area_h_lines[i + 1]
                    x1, x2 = answer_area_v_lines[j], answer_area_v_lines[j + 1]

                    margin_ratio = 0.20
                    cell_w = x2 - x1
                    cell_h = y2 - y1

                    x_margin = int(cell_w * margin_ratio)
                    y_margin = int(cell_h * margin_ratio)

                    roi_x = x1 + x_margin
                    roi_y = y1 + y_margin
                    roi_w = cell_w - (2 * x_margin)
                    roi_h = cell_h - (2 * y_margin)

                    if roi_w > 0 and roi_h > 0:
                        row_boxes.append((roi_x, roi_y, roi_w, roi_h))

            if len(row_boxes) == num_choices:
                answer_boxes.append(row_boxes)

        return answer_boxes

    # ...existing code...
    def create_id_grid_from_lines(self, h_lines, v_lines):
        # สำหรับรหัสนักศึกษา 12 หลัก จะต้องมี 12 ช่องตัวเลข (ต้องการ 13 เส้น)
        # และเมื่อรวมเส้นขอบซ้าย-ขวา จะเป็นประมาณ 14 เส้น
        # สำหรับตัวเลข 0-9 จะต้องมี 10 ช่อง (ต้องการ 11 เส้น) และเมื่อรวมเส้นหัวตารางจะประมาณ 13 เส้น
        if len(h_lines) < 13 or len(v_lines) < 14:
            app_logger.warning(
                f"ID Grid Line Detection Failed: Found {len(h_lines)} h_lines and {len(v_lines)} v_lines. Required h>=13, v>=14 for 12-digit ID."
            )
            return None

        all_digits_boxes = []
        # ใช้ v_lines[1:] เพื่อเอา 12 ช่องเลขนักศึกษา (index 1 ถึง 12)
        # หาก v_lines มี 14 เส้น เมื่อตัด v_lines[1:] จะเหลือ 13 เส้น ซึ่งพอดีกับการสร้าง 12 ช่อง
        digit_v_lines = v_lines[1:]
        digit_h_lines = h_lines[2:]

        if len(digit_h_lines) < 11 or len(digit_v_lines) < 13:
            app_logger.warning(
                f"ID Grid Slicing Failed: Got {len(digit_h_lines)} digit_h_lines and {len(digit_v_lines)} digit_v_lines. Required h>=11, v>=13."
            )
            return None

        for i in range(12): # วนลูป 12 ครั้งสำหรับรหัส 12 หลัก
            boxes_in_digit_col = []
            for j in range(10): # วนลูป 10 ครั้งสำหรับตัวเลข 0-9
                if (i + 1) < len(digit_v_lines) and (j + 1) < len(digit_h_lines):
                    x1, x2 = digit_v_lines[i], digit_v_lines[i + 1]
                    y1, y2 = digit_h_lines[j], digit_h_lines[j + 1]

                    margin_ratio = 0.20
                    cell_w = x2 - x1
                    cell_h = y2 - y1

                    x_margin = int(cell_w * margin_ratio)
                    y_margin = int(cell_h * margin_ratio)

                    roi_x = x1 + x_margin
                    roi_y = y1 + y_margin
                    roi_w = cell_w - (2 * x_margin)
                    roi_h = cell_h - (2 * y_margin)

                    if roi_w > 0 and roi_h > 0:
                        boxes_in_digit_col.append((roi_x, roi_y, roi_w, roi_h))

            all_digits_boxes.append(boxes_in_digit_col)

        return all_digits_boxes
    # ...existing code...

    def detect_marked_answer(self, thresh_image, boxes):
        if not boxes:
            return 0

        scores = []
        for x, y, w, h in boxes:
            if w <= 0 or h <= 0:
                scores.append(0)
                continue
            roi = thresh_image[y : y + h, x : x + w]
            density = cv2.countNonZero(roi) / roi.size if roi.size > 0 else 0
            scores.append(density)

        if not scores or max(scores) < 0.20:
            return 0

        max_choice = np.argmax(scores) + 1
        return max_choice

    def adaptive_threshold_for_sheet(self, gray_image):
        blurred = cv2.GaussianBlur(gray_image, (5, 5), 0)
        return cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 5
        )

    def overlay_warped_region(self, base_image, warped_region, corners):
        try:
            mask = np.zeros(base_image.shape[:2], dtype=np.uint8)
            cv2.fillPoly(mask, [corners.astype(np.int32)], 255)
            h, w = warped_region.shape[:2]
            rect = np.zeros((4, 2), dtype="float32")
            s = corners.sum(axis=1)
            rect[0] = corners[np.argmin(s)]
            rect[2] = corners[np.argmax(s)]
            diff = np.diff(corners, axis=1)
            rect[1] = corners[np.argmin(diff)]
            rect[3] = corners[np.argmax(diff)]
            src_corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
            M = cv2.getPerspectiveTransform(src_corners, rect)
            transformed_back = cv2.warpPerspective(
                warped_region, M, (base_image.shape[1], base_image.shape[0])
            )
            mask_inv = cv2.bitwise_not(mask)
            img_bg = cv2.bitwise_and(base_image, base_image, mask=mask_inv)
            img_fg = cv2.bitwise_and(transformed_back, transformed_back, mask=mask)
            combined_image = cv2.add(img_bg, img_fg)
            return combined_image
        except Exception as e:
            app_logger.error(f"Error in overlay_warped_region: {e}")
            return base_image

    def find_and_process_sheet(
        self,
        image_bytes,
        sheet_filename,
        mode="single",
        single_answer_key=None,
        multi_answer_key=None,
        session_debug_folder="debug_output",
    ):
        start_time = time.time()
        npimg = np.frombuffer(image_bytes, np.uint8)
        original_image = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
        if original_image is None:
            raise ValueError("ไม่สามารถอ่านไฟล์ภาพได้")

        height, width = original_image.shape[:2]
        if max(height, width) > 2000:
            scale = 2000 / max(height, width)
            original_image = cv2.resize(
                original_image,
                (int(width * scale), int(height * scale)),
                interpolation=cv2.INTER_AREA,
            )

        gray = cv2.cvtColor(original_image, cv2.COLOR_BGR2GRAY)
        thresh = self.adaptive_threshold_for_sheet(gray)
        all_contours, _ = cv2.findContours(
            thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        all_contours = [
            c
            for c in all_contours
            if cv2.contourArea(c)
            > (original_image.shape[0] * original_image.shape[1] * 0.001)
        ]
        id_block_contour, column_contours = self.find_main_blocks(
            all_contours, original_image.shape
        )
        if id_block_contour is None:
            raise ValueError("ไม่พบบล็อกรหัสนักศึกษา")
        if len(column_contours) != 4:
            raise ValueError(f"ไม่สามารถหาคอลัมน์ทั้ง 4 คอลัมน์ได้ (พบ {len(column_contours)})")
        column_contours = contours.sort_contours(
            column_contours, method="left-to-right"
        )[0]

        student_id = ""
        debug_blocks_image = original_image.copy()
        highlighted_image = original_image.copy()

        box_id = cv2.boxPoints(cv2.minAreaRect(id_block_contour)).astype("int")
        cv2.drawContours(debug_blocks_image, [box_id], 0, (0, 255, 0), 2)
        warped_id_thresh = four_point_transform(thresh, box_id.reshape(4, 2))
        warped_id_color = four_point_transform(original_image, box_id.reshape(4, 2))
        warped_id_highlighted = four_point_transform(
            highlighted_image, box_id.reshape(4, 2)
        )

        if warped_id_color.shape[0] > warped_id_color.shape[1] * 1.5:
            warped_id_thresh = cv2.rotate(warped_id_thresh, cv2.ROTATE_90_CLOCKWISE)
            warped_id_color = cv2.rotate(warped_id_color, cv2.ROTATE_90_CLOCKWISE)
            warped_id_highlighted = cv2.rotate(
                warped_id_highlighted, cv2.ROTATE_90_CLOCKWISE
            )

        id_grid = self.create_id_grid_from_lines(
            *self.detect_grid_lines(warped_id_thresh)
        )
        if not id_grid or len(id_grid) != 12:
            student_id = "Error Reading ID"
        else:
            for digit_boxes in id_grid:
                marked_row = self.detect_marked_answer(warped_id_thresh, digit_boxes)
                student_id += str(marked_row - 1) if marked_row > 0 else "-"
                if marked_row > 0:
                    idx = marked_row - 1
                    b = digit_boxes[idx]
                    cv2.rectangle(
                        warped_id_highlighted,
                        (b[0], b[1]),
                        (b[0] + b[2], b[1] + b[3]),
                        (0, 0, 255),
                        3,
                    )

        highlighted_image = self.overlay_warped_region(
            highlighted_image, warped_id_highlighted, box_id.reshape(4, 2)
        )
        if self.debug_mode:
            # <-- FIX 1: แก้ไข Path ของไฟล์ Debug ย่อยให้ถูกต้อง
            cv2.imwrite(
                os.path.join(
                    session_debug_folder, f"DEBUG_{sheet_filename}_id_block_result.png"
                ),
                warped_id_color,
            )

        question_counter = 1
        all_answers_data = {}
        for j, col_contour in enumerate(column_contours):
            box = cv2.boxPoints(cv2.minAreaRect(col_contour)).astype("int")
            cv2.drawContours(debug_blocks_image, [box], 0, (0, 255, 0), 2)
            warped_col_thresh = four_point_transform(thresh, box.reshape(4, 2))
            warped_col_color = four_point_transform(original_image, box.reshape(4, 2))
            warped_col_highlighted = four_point_transform(
                highlighted_image, box.reshape(4, 2)
            )

            if warped_col_color.shape[1] > warped_col_color.shape[0]:
                warped_col_thresh = cv2.rotate(
                    warped_col_thresh, cv2.ROTATE_90_COUNTERCLOCKWISE
                )
                warped_col_color = cv2.rotate(
                    warped_col_color, cv2.ROTATE_90_COUNTERCLOCKWISE
                )
                warped_col_highlighted = cv2.rotate(
                    warped_col_highlighted, cv2.ROTATE_90_COUNTERCLOCKWISE
                )

            box_rows_in_col = self.create_grid_from_lines(
                *self.detect_grid_lines(warped_col_thresh), 30, 5
            )
            if not box_rows_in_col or len(box_rows_in_col) != 30:
                for _ in range(30):
                    all_answers_data[question_counter] = {
                        "answers": set(),
                        "status": "incorrect",
                    }
                    question_counter += 1
                continue

            for boxes_for_this_question in box_rows_in_col:
                densities = [
                    cv2.countNonZero(warped_col_thresh[y : y + h, x : x + w])
                    / ((w * h) or 1)
                    for (x, y, w, h) in boxes_for_this_question
                ]
                student_answers_set = {
                    idx + 1 for idx, density in enumerate(densities) if density > 0.20
                }
                highlight_color, status = (0, 0, 255), "incorrect"
                has_multiple_answers = len(student_answers_set) > 1  # ตรวจจับการกาหลายคำตอบ
                
                if mode == "single":
                    correct_answer = single_answer_key.get(question_counter)
                    if (
                        len(student_answers_set) == 1
                        and list(student_answers_set)[0] == correct_answer
                    ):
                        highlight_color, status = (0, 255, 0), "correct"
                    elif has_multiple_answers:
                        status = "multiple_answers"  # สถานะใหม่สำหรับการกาหลายคำตอบ
                else:  # multi
                    correct_answers_set = multi_answer_key.get(question_counter, set())
                    if not correct_answers_set:
                        status = "no_key"
                    elif student_answers_set == correct_answers_set:
                        highlight_color, status = (0, 255, 0), "correct"
                    elif student_answers_set and student_answers_set.issubset(
                        correct_answers_set
                    ):
                        highlight_color, status = (0, 255, 255), "partial"
                all_answers_data[question_counter] = {
                    "answers": student_answers_set,
                    "status": status,
                    "has_multiple_answers": has_multiple_answers,  # เพิ่มข้อมูลนี้
                }
                for choice_idx, b in enumerate(boxes_for_this_question):
                    if (choice_idx + 1) in student_answers_set:
                        cv2.rectangle(
                            warped_col_highlighted,
                            (b[0], b[1]),
                            (b[0] + b[2], b[1] + b[3]),
                            highlight_color,
                            3,
                        )
                question_counter += 1

            highlighted_image = self.overlay_warped_region(
                highlighted_image, warped_col_highlighted, box.reshape(4, 2)
            )
            if self.debug_mode:
                # <-- FIX 1: แก้ไข Path ของไฟล์ Debug ย่อยให้ถูกต้อง
                cv2.imwrite(
                    os.path.join(
                        session_debug_folder,
                        f"DEBUG_{sheet_filename}_col_{j+1}_result.png",
                    ),
                    warped_col_color,
                )

        if self.debug_mode:
            cv2.imwrite(
                os.path.join(
                    session_debug_folder,
                    f"DEBUG_{mode}_{sheet_filename}_blocks_detected.png",
                ),
                debug_blocks_image,
            )

        highlighted_filename = f"highlighted_{mode}_{sheet_filename}.png"
        highlighted_filepath = os.path.join(session_debug_folder, highlighted_filename)
        cv2.imwrite(highlighted_filepath, highlighted_image)
        
        # สร้างเวอร์ชันเว็บของรูปภาพที่ highlight แล้ว
        web_highlighted_filename = f"web_{highlighted_filename}"
        web_highlighted_filepath = os.path.join(session_debug_folder, web_highlighted_filename)
        
        # แปลง OpenCV image เป็น PIL Image
        highlighted_rgb = cv2.cvtColor(highlighted_image, cv2.COLOR_BGR2RGB)
        highlighted_pil = Image.fromarray(highlighted_rgb)
        
        # สร้างเวอร์ชันเว็บที่บีบอัดแล้ว
        web_image_data = create_web_optimized_image(highlighted_pil, max_width=800, quality=60)
        with open(web_highlighted_filepath, 'wb') as f:
            f.write(web_image_data)

        app_logger.info(
            f"Processing time for {sheet_filename}: {time.time() - start_time:.2f} seconds"
        )
        return student_id, all_answers_data, web_highlighted_filename


omr_system = OMRSystemFinal()


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
        base_folder = app.config["UPLOAD_FOLDER"]
    elif folder_type == "debug_output":
        base_folder = DEBUG_FOLDER
    elif folder_type == "config":
        base_folder = STATIC_FOLDER
    else:
        raise ValueError(f"Unknown folder type: {folder_type}")
    session_specific_path = os.path.join(base_folder, session_id)
    if not os.path.exists(session_specific_path):
        os.makedirs(session_specific_path)
        app_logger.info(f"Created session directory: {session_specific_path}")
    return session_specific_path


GLOBAL_SESSION_FILE = os.path.join(STATIC_FOLDER, "global_sessions.json")


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


# === Heartbeat and Cleanup ===
HEARTBEAT_TIMEOUT_SECONDS = 5 * 60  # 5 minutes

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


def _cleanup_session_directories(session_id: str):
    paths_to_delete = [
        os.path.join(app.config["UPLOAD_FOLDER"], session_id),
        os.path.join(DEBUG_FOLDER, session_id),
        os.path.join(STATIC_FOLDER, session_id),
    ]
    for path in paths_to_delete:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
                app_logger.info(f"Removed idle session directory: {path}")
            except Exception as e:
                app_logger.error(f"Failed to delete directory {path}. Reason: {e}")


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
                app_logger.info(f"Cleaning up inactive session: {sid}")
                _cleanup_session_directories(sid)
                active_sessions.pop(sid, None)

            if to_remove:
                global_sessions["active_sessions"] = active_sessions
                save_global_session_list(global_sessions)
        except Exception as e:
            app_logger.error(f"Cleanup loop error: {e}")
        finally:
            time.sleep(check_interval)

import threading
CLEANUP_THREAD_STARTED = False



def save_session_data(data):
    try:
        config_path = get_session_path("config")
        session_file = os.path.join(config_path, "session_data.json")
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except ValueError:
        app_logger.error("Attempted to save session data without an active session.")


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
                    (df_students[1].astype(str).str.strip() + ' ' + df_students[2].astype(str).str.strip()).str.strip()
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

            score = sum(
                1 for data in answered_data.values() if data.get("status") == "correct"
            )
            student_name = student_names.get(str(student_id), "ไม่พบชื่อ")
            # Extract fname and lname from df_students if possible
            fname = ""
            lname = ""
            if str(student_id) in df_students[0].astype(str).values:
                row = df_students[df_students[0].astype(str).str.strip() == str(student_id)]
                if not row.empty:
                    fname = str(row.iloc[0,1]).strip()
                    lname = str(row.iloc[0,2]).strip() if len(row.columns) > 2 else ""
            if not fname and student_name != "ไม่พบชื่อ" and " " in student_name:
                fname, lname = student_name.split(" ", 1)
            elif not fname:
                fname = student_name
            
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
                    "student_name": f"{fname} {lname}".strip(),  # แสดงชื่อ+นามสกุลในคอลัมเดียว
                    "fname": fname,
                    "lname": lname,
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
                    (df_students[1].astype(str).str.strip() + ' ' + df_students[2].astype(str).str.strip()).str.strip()
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

            score = sum(
                1 for data in answered_data.values() if data.get("status") == "correct"
            )
            student_name = student_names.get(str(student_id), "ไม่พบชื่อ")
            # Extract fname and lname from df_students if possible
            fname = ""
            lname = ""
            if str(student_id) in df_students[0].astype(str).values:
                row = df_students[df_students[0].astype(str).str.strip() == str(student_id)]
                if not row.empty:
                    fname = str(row.iloc[0,1]).strip()
                    lname = str(row.iloc[0,2]).strip() if len(row.columns) > 2 else ""
            if not fname and student_name != "ไม่พบชื่อ" and " " in student_name:
                fname, lname = student_name.split(" ", 1)
            elif not fname:
                fname = student_name
            
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
                "student_name": f"{fname} {lname}".strip(),
                "fname": fname,
                "lname": lname,
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


def clear_folder(folder_path):
    if not os.path.exists(folder_path):
        return
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
        except Exception as e:
            app_logger.error(f"Failed to delete {file_path}. Reason: {e}")


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

    # session.clear()
    # app_logger.info(
    #     "Session data cleared. A new session will be generated on next request."
    # )

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
    """ตรวจสอบว่าระบบรองรับการแปลง PDF หรือไม่"""
    poppler_installed = check_poppler_installation()
    return jsonify(
        {
            "pdf_supported": poppler_installed,
            "message": (
                "PDF conversion is supported"
                if poppler_installed
                else "Poppler is not installed"
            ),
        }
    )



def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def check_poppler_installation():
    """ตรวจสอบว่า Poppler ติดตั้งแล้วหรือไม่"""
    try:
        import subprocess

        # เพิ่ม path ของ poppler ที่เราติดตั้งไว้
        poppler_path = os.path.join(
            os.getcwd(), "poppler", "poppler-24.08.0", "Library", "bin"
        )
        if os.path.exists(poppler_path):
            os.environ["PATH"] = poppler_path + os.pathsep + os.environ.get("PATH", "")

        result = subprocess.run(
            ["pdftoppm", "-h"], capture_output=True, text=True, timeout=5
        )
        return True
    except (
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
        FileNotFoundError,
    ):
        return False


def create_web_optimized_image(pil_image, max_width=800, quality=60):
    """
    สร้างรูปภาพที่ปรับขนาดและบีบอัดสำหรับแสดงผลบนเว็บ
    """
    # คำนวณขนาดใหม่โดยรักษาอัตราส่วน
    width, height = pil_image.size
    if width > max_width:
        ratio = max_width / width
        new_width = max_width
        new_height = int(height * ratio)
        pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # บันทึกเป็น JPEG ที่บีบอัดแล้ว
    buffer = io.BytesIO()
    pil_image.save(buffer, format='JPEG', quality=quality, optimize=True)
    return buffer.getvalue()


def convert_pdf_to_images(pdf_bytes, original_filename, save_path):
    try:
        if not check_poppler_installation():
            raise ValueError("ระบบขาด Poppler - กรุณาติดตั้ง Poppler ก่อนใช้งานฟีเจอร์ PDF")

        # แปลง PDF เป็นรูปภาพ DPI สูงสำหรับการประมวลผล
        images = convert_from_bytes(pdf_bytes, dpi=300, fmt="jpeg")
        if not images:
            raise ValueError("ไม่พบหน้าใดๆ ในไฟล์ PDF")

        converted_files = []
        base_filename = os.path.splitext(original_filename)[0]

        for i, image in enumerate(images, 1):
            page_filename = f"{base_filename}_page_{i:03d}.jpg"
            saved_filename = f"{uuid.uuid4().hex}_{page_filename}"
            
            # บันทึกรูปภาพต้นฉบับ DPI สูงสำหรับการประมวลผล
            original_filepath = os.path.join(save_path, saved_filename)
            image.save(original_filepath, "JPEG", quality=95)
            
            # สร้างรูปภาพเวอร์ชันเว็บที่บีบอัดแล้ว
            web_filename = f"web_{saved_filename}"
            web_filepath = os.path.join(save_path, web_filename)
            web_image_data = create_web_optimized_image(image, max_width=800, quality=60)
            
            with open(web_filepath, 'wb') as f:
                f.write(web_image_data)

            converted_files.append(
                {
                    "original_name": page_filename,
                    "saved_name": saved_filename,
                    "web_name": web_filename,  # เพิ่มชื่อไฟล์เวอร์ชันเว็บ
                    "url": f"/uploads/{session['session_id']}/{web_filename}",  # ใช้เวอร์ชันเว็บสำหรับแสดงผล
                    "original_url": f"/uploads/{session['session_id']}/{saved_filename}",  # เก็บ URL ต้นฉบับไว้สำหรับประมวลผล
                }
            )

        app_logger.info(
            f"Converted PDF '{original_filename}' to {len(converted_files)} images (with web optimization)"
        )
        return converted_files
    except Exception as e:
        app_logger.error(f"Error converting PDF '{original_filename}': {e}")
        raise ValueError(f"ไม่สามารถแปลงไฟล์ PDF ได้: {str(e)}")


def clean_image_file(filepath):
    """
    อ่านไฟล์ภาพ, ใช้ adaptive thresholding เพื่อทำให้พื้นหลังขาวสะอาด,
    และเขียนทับไฟล์เดิม
    """
    try:
        image = cv2.imread(filepath)
        if image is None:
            app_logger.error(f"Could not read image for cleaning: {filepath}")
            return False

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        cleaned_image = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=31,
            C=15,
        )

        cleaned_bgr = cv2.cvtColor(cleaned_image, cv2.COLOR_GRAY2BGR)

        cv2.imwrite(filepath, cleaned_bgr)
        app_logger.info(f"Successfully cleaned image: {os.path.basename(filepath)}")
        return True
    except Exception as e:
        app_logger.error(f"Error cleaning image {os.path.basename(filepath)}: {e}")
        return False


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
