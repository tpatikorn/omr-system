import os
import time
import cv2
import numpy as np
from PIL import Image
from imutils import contours
from imutils.perspective import four_point_transform

from image_util import create_web_optimized_image
from logging_manager import get_logger


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
            get_logger().warning(
                f"Answer Grid Line Detection Failed: Found {len(h_lines)} h_lines and {len(v_lines)} v_lines. Required h>={num_questions + 3}, v>={num_choices + 2}."
            )
            return None

        answer_boxes = []
        answer_area_h_lines = h_lines[3:]
        answer_area_v_lines = v_lines[1:]

        if (
                len(answer_area_h_lines) <= num_questions
                or len(answer_area_v_lines) <= num_choices
        ):
            get_logger().warning(
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
            get_logger().warning(
                f"ID Grid Line Detection Failed: Found {len(h_lines)} h_lines and {len(v_lines)} v_lines. Required h>=13, v>=14 for 12-digit ID."
            )
            return None

        all_digits_boxes = []
        # ใช้ v_lines[1:] เพื่อเอา 12 ช่องเลขนักศึกษา (index 1 ถึง 12)
        # หาก v_lines มี 14 เส้น เมื่อตัด v_lines[1:] จะเหลือ 13 เส้น ซึ่งพอดีกับการสร้าง 12 ช่อง
        digit_v_lines = v_lines[1:]
        digit_h_lines = h_lines[2:]

        if len(digit_h_lines) < 11 or len(digit_v_lines) < 13:
            get_logger().warning(
                f"ID Grid Slicing Failed: Got {len(digit_h_lines)} digit_h_lines and {len(digit_v_lines)} digit_v_lines. Required h>=11, v>=13."
            )
            return None

        for i in range(12):  # วนลูป 12 ครั้งสำหรับรหัส 12 หลัก
            boxes_in_digit_col = []
            for j in range(10):  # วนลูป 10 ครั้งสำหรับตัวเลข 0-9
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
            roi = thresh_image[y: y + h, x: x + w]
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
            _m = cv2.getPerspectiveTransform(src_corners, rect)
            transformed_back = cv2.warpPerspective(
                warped_region, _m, (base_image.shape[1], base_image.shape[0])
            )
            mask_inv = cv2.bitwise_not(mask)
            img_bg = cv2.bitwise_and(base_image, base_image, mask=mask_inv)
            img_fg = cv2.bitwise_and(transformed_back, transformed_back, mask=mask)
            combined_image = cv2.add(img_bg, img_fg)
            return combined_image
        except Exception as e:
            get_logger().error(f"Error in overlay_warped_region: {e}")
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
                    cv2.countNonZero(warped_col_thresh[y: y + h, x: x + w])
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
                        f"DEBUG_{sheet_filename}_col_{j + 1}_result.png",
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

        get_logger().info(
            f"Processing time for {sheet_filename}: {time.time() - start_time:.2f} seconds"
        )
        return student_id, all_answers_data, web_highlighted_filename
