#!/bin/bash
# ==============================================================================
# Nextcloud Integration Wrapper Script
# ==============================================================================
# Skrip ini dipanggil oleh Nextcloud (misalnya via files_antivirus Executable Mode
# atau Nextcloud Workflow / Flow script).
#
# Argumen $1: Path file yang baru saja diupload ke Nextcloud
#
# Exit Code:
#   0 : File Bersih -> Nextcloud mengizinkan upload
#   1 : File Ditolak (Seksualitas / Kekerasan) -> Nextcloud menggagalkan upload
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${SCRIPT_DIR}/.venv/bin/python"
MODERATE_SCRIPT="${SCRIPT_DIR}/moderate.py"

TARGET_FILE="$1"
NEXTCLOUD_FILE_ID="$2"

if [ -z "$TARGET_FILE" ]; then
    echo "[Nextcloud Scanner] Error: Tidak ada file yang diberikan." >&2
    exit 2
fi

# Jalankan moderasi dengan python virtualenv. File ID bersifat optional dan
# hanya diperlukan bila action_on_reject=delete memakai OCC.
if [ -n "$NEXTCLOUD_FILE_ID" ]; then
    "$PYTHON_BIN" "$MODERATE_SCRIPT" "$TARGET_FILE" --file-id "$NEXTCLOUD_FILE_ID"
else
    "$PYTHON_BIN" "$MODERATE_SCRIPT" "$TARGET_FILE"
fi
EXIT_CODE=$?

# Nextcloud files_antivirus menganggap exit code 1 sebagai file berbahaya/terinfeksi
# dan langsung menolak penyimpanan file ke storage pengguna.
exit $EXIT_CODE
