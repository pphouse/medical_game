"""SM-2 spaced-repetition scheduling.

quality: 0-5 self-assessment score, mapped from the app's 5-level mastery
buttons (◎/○/△/✕/未演習) via MASTERY_TO_QUALITY.
"""
from datetime import timedelta

from django.utils import timezone

MASTERY_TO_QUALITY = {
    "double_circle": 5,
    "circle": 4,
    "triangle": 3,
    "cross": 1,
    "unstudied": 0,
}

MIN_EASE_FACTOR = 1.3


def schedule_next_review(*, interval_days: float, ease_factor: float, quality: int):
    """Returns (next_interval_days, next_ease_factor, next_review_at)."""
    if quality < 3:
        next_interval = 1.0
    elif interval_days <= 1:
        next_interval = 1.0
    elif interval_days <= 6:
        next_interval = 6.0
    else:
        next_interval = round(interval_days * ease_factor, 2)

    next_ease_factor = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    next_ease_factor = max(MIN_EASE_FACTOR, round(next_ease_factor, 2))

    next_review_at = timezone.now() + timedelta(days=next_interval)
    return next_interval, next_ease_factor, next_review_at
