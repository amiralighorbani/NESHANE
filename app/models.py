"""مدل‌های داده: درخواست فال، بلوک‌های خوانش و نتیجهٔ کامل."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class SignInfo(BaseModel):
    key: str
    name: str
    symbol: str
    range: str
    element: str
    element_glyph: str
    planet: str
    mode: str
    traits: List[str]
    strengths: List[str]
    shadow: str
    motto: str
    love_style: str
    work_style: str
    care: str
    lucky_day: str


class FortuneRequest(BaseModel):
    """اطلاعاتی که کاربر وارد می‌کند."""

    name: str
    gender: str = ""
    jy: int = 1370
    jm: int = 1
    jd: int = 1
    birth_time: str = ""
    city: str = ""
    topic: str = "general"
    intent: str = ""
    method: str = "hafez"

    @property
    def birth_label(self) -> str:
        from .utils import jalali_label

        return jalali_label(self.jy, self.jm, self.jd)


class ReadingBlock(BaseModel):
    """یک کارت از خوانش؛ برای هر روش فال متفاوت پر می‌شود.

    `visual` و `symbols` همان چیزی هستند که هر فال را از فال دیگر جدا می‌کنند:
    تاروت سه کارت واقعی می‌اندازد، تاس سه تاسِ نشان‌دار می‌اندازد، رون یک سنگ
    می‌گذارد و الگوهای عددی/چینی نماد خودشان را دارند.
    """

    key: str
    title: str
    icon: str = ""
    accent: str = ""
    lead: str = ""
    body: str = ""
    lines: List[str] = Field(default_factory=list)
    meta: Dict[str, str] = Field(default_factory=dict)
    note: str = ""
    # نوع نمایش نمادین: cards | dice | rune | glyph | verses | animal | none
    visual: str = ""
    # جزئیات نمادهای درآمده (اسم، شماره، پیکان، جهت، توضیح کوتاه…)
    symbols: List[Dict[str, str]] = Field(default_factory=list)
    visual_label: str = ""


class EnergyReading(BaseModel):
    key: str
    label: str
    icon: str
    value: int
    band: str
    note: str


class LuckyItem(BaseModel):
    label: str
    value: str
    icon: str
    hint: str = ""


class MoodInfo(BaseModel):
    label: str
    icon: str
    line: str


class DayPlanet(BaseModel):
    weekday: str
    planet: str
    element: str
    icon: str = ""
    note: str
    affinity: str
    affinity_line: str


class DayPhase(BaseModel):
    label: str
    icon: str
    note: str
    energy: int


class CompatInfo(BaseModel):
    sign_name: str
    symbol: str
    affinity: str
    line: str
    score: int


class Reading(BaseModel):
    """نتیجهٔ کامل فال؛ همان چیزی که صفحه را می‌سازد."""

    token: str
    created_label: str
    name: str
    gender: str = ""
    city: str = ""
    birth_label: str
    birth_time_label: str = ""
    sign: SignInfo
    topic_key: str
    topic_label: str
    topic_icon: str
    intent: str = ""
    method_key: str
    method_label: str
    method_icon: str = ""
    method_accent: str = ""
    headline: str
    summary: str
    mood: MoodInfo
    energies: List[EnergyReading]
    overall: int
    overall_label: str
    overall_note: str
    element_note: str
    day_planet: DayPlanet
    blocks: List[ReadingBlock] = Field(default_factory=list)
    lucky: List[LuckyItem] = Field(default_factory=list)
    lucky_color_hex: str = "#6b4fbb"
    dos: List[str] = Field(default_factory=list)
    donts: List[str] = Field(default_factory=list)
    compat: CompatInfo
    affirmation: str
    phases: List[DayPhase] = Field(default_factory=list)
    curve: List[int] = Field(default_factory=list)
    curve_labels: List[str] = Field(default_factory=list)
    peak_label: str = ""
    power_note: str = ""
    summary_text: str = ""
    seed: str = ""
    # خوانش شخصی که مدل زبانی بر پایهٔ نیتِ کاربر نوشته است (اگر موفق بوده باشد).
    ai_note: str = ""
    ai_guidance: List[str] = Field(default_factory=list)
    ai_invitation: str = ""
    ai_meta: Dict[str, Any] = Field(default_factory=dict)


class TestResult(BaseModel):
    """نتیجهٔ یک تست شخصیت."""

    test_key: str
    test_label: str
    test_icon: str = ""
    accent: str = ""
    code: str
    title: str
    icon: str = ""
    glyph: str = ""
    tagline: str = ""
    body: str = ""
    gift: str = ""
    shadow: str = ""
    advice: str = ""
    partner: str = ""
    strengths: List[str] = Field(default_factory=list)
    careers: List[str] = Field(default_factory=list)
    love: str = ""
    scores: Dict[str, int] = Field(default_factory=dict)
    axes: List[Dict[str, str]] = Field(default_factory=list)
    ranked: List[Dict[str, str]] = Field(default_factory=list)
    created_label: str = ""
    attempt_id: int = 0
    # تعداد پرسش‌های پاسخ‌داده‌شده و خلاصهٔ خوانای نتیجه (برای تفسیر مدل زبانی).
    answered: int = 0
    breakdown: str = ""
    has_signal: bool = True
    # تفسیر شخصی که مدل زبانی بر پایهٔ همین پاسخ‌ها نوشته است.
    ai_note: str = ""
    ai_next_step: str = ""
    ai_meta: Dict[str, Any] = Field(default_factory=dict)
