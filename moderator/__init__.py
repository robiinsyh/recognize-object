"""
Sistem Moderasi Konten Multimedia (Foto & Video) untuk Nextcloud.
Mendeteksi konten seksualitas/pornografi dan kekerasan/gore/senjata.
"""

from .detector import ContentModerator

__all__ = ["ContentModerator"]
