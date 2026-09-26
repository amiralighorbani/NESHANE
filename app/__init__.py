"""نشانه — پلتفرم فال (FastAPI + Jinja2 SSR)."""

__version__ = "1.0.0"

# متغیرهای محیطی و کلیدهای حساس از `.env` خوانده می‌شوند. این کار باید پیش از
# هر ماژول دیگری انجام شود، چون بعضی ماژول‌ها (مثل `admin_auth` و `llm`) مقدارشان
# را همان لحظهٔ import می‌خوانند.
from . import env as _env  # noqa: E402

_env.ensure_loaded()

__all__ = ["__version__"]
