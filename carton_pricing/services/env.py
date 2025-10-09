# carton_pricing/services/env.py
from __future__ import annotations
import os
from pathlib import Path

class Env:
    """
    خواندن ساده متغیرهای محیطی با مقدار پیش‌فرض.
    base_dir صرفاً برای نیازهای بعدی نگه داشته شده.
    """
    def __init__(self, base_dir: str | Path | None = None):
        # ریشهٔ پروژه را اگر لازم شد داشته باشیم
        self.base_dir = Path(base_dir or Path(__file__).resolve().parents[2])

    def str(self, key: str, default: str | None = None) -> str | None:
        return os.environ.get(key, default)

    def bool(self, key: str, default: bool = False) -> bool:
        v = os.environ.get(key)
        if v is None:
            return default
        return v.strip().lower() in ("1", "true", "yes", "on")

    def int(self, key: str, default: int = 0) -> int:
        v = os.environ.get(key)
        try:
            return int(v) if v is not None else default
        except Exception:
            return default


class SettingsLoader:
    """
    یک Loader ساده برای استفاده در settings.py یا سرویس‌های دیگر.
    """
    def __init__(self, base_dir: str | Path | None = None):
        self.env = Env(base_dir=base_dir)

    def db_url(self) -> str | None:
        # مثال: خواندن DATABASE_URL (اگر داری)
        return self.env.str("DATABASE_URL")

    def secret_key(self) -> str:
        return self.env.str("DJANGO_SECRET_KEY", "dev-insecure-secret-please-change")

    def debug(self) -> bool:
        return self.env.bool("DJANGO_DEBUG", True)
