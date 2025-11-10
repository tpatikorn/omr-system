# === Helper Functions for Dynamic Base URL ===
import os

import socket
import netifaces


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
    # ถ้ามี netifaces ให้ใช้
    for interface in netifaces.interfaces():
        addresses = netifaces.ifaddresses(interface)
        if netifaces.AF_INET in addresses:
            for addr in addresses[netifaces.AF_INET]:
                ip = addr['addr']
                if not ip.startswith('127.') and not ip.startswith('169.254.'):
                    return ip

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
