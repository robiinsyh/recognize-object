#!/bin/bash
FILE_PATH="$1"
FILE_ID="$2"
NC_USER="$3"
# Jalankan moderasi
/var/www/html/recz-object/venv/bin/python3 /var/www/html/recz-object/moderate.py \
  "$FILE_PATH" \
  --engine sightengine \
  --file-id "$FILE_ID"
EXIT_CODE=$?
# Jika file ditolak (exit code 1), kosongkan trash agar permanent delete
if [ "$EXIT_CODE" -eq 1 ] && [ -n "$NC_USER" ]; then
  php /var/www/html/occ trashbin:cleanup "$NC_USER" --force > /dev/null 2>&1
fi
