import logging

from werkzeug.serving import WSGIRequestHandler

__app_logger = None

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


def setup_logging(app_instance):
    global __app_logger
    if __app_logger is not None:
        return __app_logger

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
    __app_logger = logging.getLogger("omr_app")
    __app_logger.setLevel(logging.INFO)

    return __app_logger

def get_logger():
    return __app_logger