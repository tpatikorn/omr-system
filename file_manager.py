import os

from logging_manager import get_logger


def clear_folder(folder_path):
    if not os.path.exists(folder_path):
        return
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
        except Exception as e:
            get_logger().error(f"Failed to delete {file_path}. Reason: {e}")
