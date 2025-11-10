import io
import os
import pymupdf
import cv2
from PIL import Image
from flask import session

from manager.logging_manager import get_logger


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
        doc = pymupdf.open(stream=pdf_bytes)
        converted_files = []

        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            pix = page.get_pixmap()
            image_filename = f"{original_filename}_{page_num + 1}.png"
            pix.save(os.path.join(save_path, image_filename))

            pil_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # สร้างรูปภาพเวอร์ชันเว็บที่บีบอัดแล้ว
            web_filename = f"web_{image_filename}"
            web_filepath = os.path.join(save_path, web_filename)
            web_image_data = create_web_optimized_image(pil_img, max_width=800, quality=60)

            with open(web_filepath, 'wb') as f:
                f.write(web_image_data)

            converted_files.append(
                {
                    "original_name": original_filename,
                    "saved_name": image_filename,
                    "web_name": web_filename,  # เพิ่มชื่อไฟล์เวอร์ชันเว็บ
                    "url": f"/uploads/{session['session_id']}/{web_filename}",  # ใช้เวอร์ชันเว็บสำหรับแสดงผล
                    "original_url": f"/uploads/{session['session_id']}/{image_filename}",
                    # เก็บ URL ต้นฉบับไว้สำหรับประมวลผล
                }
            )

        get_logger().info(
            f"Converted PDF '{original_filename}' to {len(converted_files)} images (with web optimization)"
        )
        return converted_files
    except Exception as e:
        get_logger().error(f"Error converting PDF '{original_filename}': {e}")
        raise ValueError(f"ไม่สามารถแปลงไฟล์ PDF ได้: {str(e)}")


def clean_image_file(filepath):
    """
    อ่านไฟล์ภาพ, ใช้ adaptive thresholding เพื่อทำให้พื้นหลังขาวสะอาด,
    และเขียนทับไฟล์เดิม
    """
    try:
        image = cv2.imread(filepath)
        if image is None:
            get_logger().error(f"Could not read image for cleaning: {filepath}")
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
        get_logger().info(f"Successfully cleaned image: {os.path.basename(filepath)}")
        return True
    except Exception as e:
        get_logger().error(f"Error cleaning image {os.path.basename(filepath)}: {e}")
        return False
