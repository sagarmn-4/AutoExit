"""
cleanup_project.py
Safely removes unnecessary cache/log/temp files without touching
the virtual environment or core project files.
Now reports total items deleted and total space freed.
"""

import os
import shutil
import logging

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

CLEAN_TARGETS = [
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".vscode",
    ".idea",
    "build",
    "dist",
]

CLEAN_EXTENSIONS = [
    ".pyc", ".pyo", ".pyd", ".log", ".tmp", ".bak", ".zip", ".csv"
]

EXCLUDE_DIRS = ["venv", "env", ".git", ".hg", ".svn", "__pypackages__"]
EXCLUDE_FILES = [".env", "config.json", "requirements.txt"]

deleted_files = 0
deleted_folders = 0
freed_bytes = 0

def get_size(path):
    try:
        return os.path.getsize(path)
    except Exception:
        return 0

def safe_remove_file(file_path):
    global deleted_files, freed_bytes
    try:
        if any(ex in file_path for ex in EXCLUDE_DIRS):
            return
        if os.path.basename(file_path) in EXCLUDE_FILES:
            return
        file_size = get_size(file_path)
        os.remove(file_path)
        deleted_files += 1
        freed_bytes += file_size
        logging.info(f"Deleted file: {file_path}")
    except Exception as e:
        logging.warning(f"Could not delete file: {file_path} ({e})")

def safe_remove_dir(dir_path):
    global deleted_folders
    try:
        if any(ex in dir_path for ex in EXCLUDE_DIRS):
            return
        size_before = 0
        for root, _, files in os.walk(dir_path):
            for f in files:
                size_before += get_size(os.path.join(root, f))
        shutil.rmtree(dir_path, ignore_errors=True)
        deleted_folders += 1
        logging.info(f"Deleted folder: {dir_path}")
        return size_before
    except Exception as e:
        logging.warning(f"Could not delete folder: {dir_path} ({e})")
        return 0

def cleanup():
    global freed_bytes
    logging.info("Starting safe project cleanup...")

    for root, dirs, files in os.walk(".", topdown=False):
        if any(skip in root for skip in EXCLUDE_DIRS):
            continue

        for name in files:
            file_path = os.path.join(root, name)
            if any(name.endswith(ext) for ext in CLEAN_EXTENSIONS):
                safe_remove_file(file_path)

        for name in dirs:
            dir_path = os.path.join(root, name)
            if name in CLEAN_TARGETS or name == "__pycache__":
                freed_bytes += safe_remove_dir(dir_path) or 0

    freed_mb = round(freed_bytes / (1024 * 1024), 2)
    logging.info("----------------------------------------")
    logging.info(f"Cleanup complete:")
    logging.info(f"  Files deleted   : {deleted_files}")
    logging.info(f"  Folders deleted : {deleted_folders}")
    logging.info(f"  Space freed     : {freed_mb} MB")
    logging.info("----------------------------------------")

if __name__ == "__main__":
    cleanup()
