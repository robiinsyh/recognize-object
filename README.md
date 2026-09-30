# Sistem Moderasi Konten Multimedia (Foto & Video) untuk Nextcloud

Sistem analisis dan filter otomatis foto dan video terhadap pelanggaran konten berunsur:
1. **Seksualitas / Pornografi** (Ketelanjangan penuh/sebagian, pose eksplisit, pornografi).
2. **Kekerasan / Gore / Senjata** (Senjata api, pisau, darah/luka pekat, tindakan kekerasan fisik).

Sistem ini didesain khusus untuk **Nextcloud**, sehingga setiap kali ada file foto/video yang diupload oleh pengguna dan melanggar aturan, file tersebut **otomatis ditolak/direject** (mengembalikan standard Linux Exit Code `1` untuk membatalkan proses upload).

---

## 🛠️ Fitur Utama

- **Dual-Engine Detection**:
  - **Gemini Vision AI (Akurasi Tinggi)**: Menggunakan Google Gemini Multimodal Vision API untuk pemahaman konteks visual yang sangat mendalam dan akurat.
  - **Sightengine Vision API**: Alternatif cloud untuk moderasi nudity, kekerasan, gore, dan weapon pada foto maupun video.
  - **Local Offline Engine (Tanpa Internet / GPU)**: Analisis segmentasi kromatisitas kulit manusia (YCbCr + RGB Kovac Algorithm) dan distribusi spektrum merah darah/luka pekat secara lokal dalam hitungan milidetik.
- **Dukungan Format Lengkap**:
  - **Foto**: JPG, JPEG, PNG, WEBP, GIF, BMP, TIFF.
  - **Video**: MP4, MKV, AVI, MOV, WEBM, FLV, WMV, M4V (Frame diekstrak otomatis menggunakan `ffmpeg`).
- **Integrasi Penuh Nextcloud**:
  - Kompatibel dengan aplikasi Nextcloud **Antivirus for files (`files_antivirus`)** dalam mode Executable.
  - Kompatibel dengan **Nextcloud Flow / Workflow Script**.
  - Dilengkapi daemon pemantau otomatis (`nextcloud_watcher.py`).
- **Pencatatan Audit (Logging)**: Semua file yang diperiksa dicatat ke dalam `moderation.log`.

---

## 📁 Struktur Direktori

```text
Recognize-object/
├── .venv/                   # Virtual Environment Python
├── config.json              # File konfigurasi utama (ambang batas, engine, ffmpeg)
├── .env copy.example        # Contoh template credential Gemini dan Sightengine
├── requirements.txt         # Daftar pustaka dependensi Python
├── moderate.py              # CLI scanner utama (mengembalikan Exit Code 0 atau 1)
├── nextcloud_scanner.sh     # Wrapper script bash siap pakai untuk Nextcloud
├── nextcloud_watcher.py     # Daemon background pemantau folder data Nextcloud
├── test_moderation.py       # Skrip pengujian otomatis
├── moderation.log           # Log aktivitas pemindaian file
└── moderator/
    ├── __init__.py
    ├── config.py            # Loader konfigurasi
    ├── detector.py          # Orchestrator utama moderasi
    ├── gemini_engine.py     # Engine Google Gemini Vision
    ├── local_engine.py      # Engine Heuristic & ONNX lokal
    └── video_utils.py       # Ekstraksi frame video via ffmpeg
```

---

## 🚀 Cara Menjalankan & Menguji Secara Mandiri

### 1. Menjalankan Tes Otomatis
Untuk memverifikasi bahwa sistem bekerja mendeteksi foto aman, foto seksualitas sintetis, foto darah/luka sintetis, serta video:
 ```bash
.venv/bin/python test_moderation.py
.venv/bin/python test_sightengine.py
```

### 2. Memeriksa File Gambar
```bash
.venv/bin/python moderate.py /path/to/gambar.jpg
.venv/bin/python moderate.py /path/to/gambar.jpg --engine sightengine
.venv/bin/python moderate.py /path/to/video.mp4 --engine gemini

#pengujian agar file berisi konten sensitive bisa dieksekusi dengan cara penghapusan oleh occ
/var/www/html/recz-object/venv/bin/python3 moderate.py /path/to/konten_sensitif.jpg \
  --engine sightengine \
  --file-id "12345" \
  --action-on-reject delete \
  --occ-path /var/www/html/occ
```
Output jika bersih (**Exit Code: 0**):
```text
============================================================
 HASIL PEMERIKSAAN KONTEN: ✅ ALLOWED
============================================================
 File        : /path/to/gambar.jpg
 Tipe        : IMAGE
 Engine      : local_heuristic
 Seksualitas : 0.00 (Batas: 0.60)
 Kekerasan   : 0.00 (Batas: 0.60)
 Keterangan  : Normal skin coverage (0.0%). No excessive blood/gore pattern (0.0%)
============================================================
```

Output jika melanggar (**Exit Code: 1**):
```text
============================================================
 HASIL PEMERIKSAAN KONTEN: ❌ REJECTED
============================================================
 File        : /path/to/gambar_vulgar.jpg
 Tipe        : IMAGE
 Engine      : local_heuristic
 Seksualitas : 1.00 (Batas: 0.60)
 Kekerasan   : 0.00 (Batas: 0.60)
 Keterangan  : High exposed skin coverage (100.0%). No excessive blood/gore pattern (0.0%)

[ALASAN PENOLAKAN]
  • Sexuality score (1.00 >= 0.6)
============================================================
```

### 3. Memeriksa File Video
```bash
.venv/bin/python moderate.py /path/to/video.mp4
```
Sistem akan mengekstrak frame video setiap interval waktu tertentu (default: 2 detik sekali via `ffmpeg`), lalu mengevaluasi setiap frame. Jika salah satu frame melanggar, video langsung ditolak.

### 4. Output Format JSON
Gunakan flag `--json` jika ingin diintegrasikan ke API atau skrip lain:
```bash
.venv/bin/python moderate.py /path/to/gambar.jpg --json
```

---

## ⚙️ Konfigurasi (`config.json`)

Anda dapat menyesuaikan sensitivitas pada file `config.json`:
```json
{
  "engine": "auto",
  "gemini": {
    "api_key": "",
    "model": "gemini-2.5-flash"
  },
  "sightengine": {
    "api_user": "",
    "api_secret": "",
    "models": "nudity-2.1,violence,weapon,gore-2.0",
    "timeout_seconds": 90
  },
  "thresholds": {
    "sexuality": 0.6,
    "violence": 0.6
  },
  "video": {
    "sample_interval_seconds": 2.0,
    "max_frames": 15,
    "ffmpeg_path": "ffmpeg"
  },
  "nextcloud": {
    "reject_exit_code": 1,
    "clean_exit_code": 0,
    "error_exit_code": 2,
    "log_file": "moderation.log",
    "action_on_reject": "none",
    "occ_path": "",
    "occ_php": "php",
    "occ_timeout_seconds": 30,
    "quarantine_dir": ""
  }
}
```

- **`engine`**:
  - `"auto"`: Memilih Sightengine jika credential terisi, lalu Gemini jika API key terisi, lalu fallback ke engine lokal offline.
  - `"gemini"`: Memaksa menggunakan Google Gemini Vision AI.
  - `"sightengine"`: Memaksa menggunakan Sightengine API untuk foto dan video.
  - `"local"`: Menggunakan analisis heuristik lokal (sepenuhnya offline tanpa internet).
- **`gemini.api_key`**: Kunci API dari Google AI Studio (bisa didapatkan gratis di [aistudio.google.com](https://aistudio.google.com/)) atau melalui environment variable `GEMINI_API_KEY`.
- **`sightengine.api_user` / `sightengine.api_secret`**: Credential dari dashboard Sightengine atau environment variable `SIGHTENGINE_API_USER` dan `SIGHTENGINE_API_SECRET`.
- **`sightengine.models`**: Model yang dikirim ke Sightengine. Default: `nudity-2.1,violence,weapon,gore-2.0`.
- **`thresholds`**: Nilai ambang batas deteksi (0.0 - 1.0). Semakin kecil nilainya, semakin ketat filter.
- **`nextcloud.action_on_reject`**: Default `none`. Nilai `delete` menghapus file memakai `occ files:delete --force -- <file_id>`, bukan menghapus path filesystem secara langsung.
- **`nextcloud.occ_path`**: Path absolut ke file `occ`, misalnya `/var/www/html/nextcloud/occ`.

### Penghapusan via OCC dari Workflow Script

Fitur penghapusan sengaja **nonaktif secara default**. Untuk mengaktifkannya, isi konfigurasi:

```json
"nextcloud": {
  "action_on_reject": "delete",
  "occ_path": "/var/www/html/nextcloud/occ",
  "occ_php": "php",
  "occ_timeout_seconds": 30
}
```

Kemudian panggil CLI dari Workflow Script dengan file ID `%i`:

```bash
/var/www/html/recz-object/recz/venv/bin/python /var/www/html/recz-object/recz/moderate.py "%f" --engine sightengine --file-id "%i"
```

Sebelum mengaktifkan, pastikan command berikut tersedia pada instalasi Nextcloud Anda:

```bash
sudo -u www-data php /var/www/html/nextcloud/occ list | grep files:delete
```

Jika `files:delete` tidak tersedia pada versi Nextcloud Anda, biarkan `action_on_reject` bernilai `none`; jangan mengganti dengan `rm` terhadap path storage secara langsung.

---

## ☁️ Panduan Integrasi ke Nextcloud (Agar Otomatis Reject)

### Metode 1: Menggunakan Nextcloud App "Antivirus for files" (Sangat Direkomendasikan)
Nextcloud memiliki aplikasi resmi bawaan bernama **Antivirus for files (`files_antivirus`)** yang bertugas memeriksa file tepat saat diupload. Jika scanner mengembalikan exit code 1, Nextcloud akan langsung **menghentikan upload dan menolak file tersebut di antarmuka web**:

1. Masuk ke Nextcloud sebagai **Administrator**.
2. Masuk ke menu **Apps** (Aplikasi), cari dan pasang aplikasi **"Antivirus for files"** (`files_antivirus`).
3. Buka **Administration settings** (Pengaturan Admin) -> **Security** (Keamanan) -> Bagian **Antivirus for files**.
4. Atur pengaturannya:
   - **Antivirus Mode**: Pilih **Executable**.
   - **Path to executable**: Masukkan path absolut ke skrip wrapper:
     ```text
     /home/robiezet/Documents/Robi Backup/career/Recognize-object/nextcloud_scanner.sh
     ```
   - **When infected files are found**: Pilih **Only log** atau **Delete file immediately / Reject upload**.
5. Simpan pengaturan. Selesai! Kini setiap pengguna mengunggah foto atau video yang mengandung pornografi atau kekerasan, Nextcloud akan langsung menolaknya.

---

### Metode 2: Menggunakan Nextcloud Flow / Workflow Script
Jika menggunakan modul Nextcloud Flow:
1. Pasang aplikasi **Workflow script** (`workflow_script`).
2. Masuk ke **Administration settings** -> **Workflow**.
3. Buat aturan baru:
   - **Trigger**: File created / File uploaded.
   - **Operation**: Execute script.
   - **Script path**:
     ```text
     /home/robiezet/Documents/Robi Backup/career/Recognize-object/nextcloud_scanner.sh %n
     ```
   - Di mana `%n` adalah placeholder path file yang disediakan Nextcloud.

---

### Metode 3: Background Directory Watcher Daemon
Jika Anda ingin memantau direktori data Nextcloud secara berkala/real-time di server:
```bash
.venv/bin/python nextcloud_watcher.py /var/www/nextcloud/data/
```
Watcher ini akan mendeteksi setiap kali ada file gambar/video baru di folder data Nextcloud, memindainya, dan otomatis menghapus atau memindahkan file terlarang ke folder karantina.

---

## 🔍 Log Pemindaian
Setiap aktivitas pemindaian otomatis tersimpan dalam file `moderation.log`:
```text
[2026-09-28 10:34:53,905] WARNING: Verdict: REJECT | File: /path/to/upload.jpg | Sexuality: 1.00 | Violence: 0.00 | Engine: local_heuristic | Details: High exposed skin coverage (100.0%)
```
