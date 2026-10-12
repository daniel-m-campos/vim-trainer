"""Model constants shared with app/src/model/model.ts (keep the two in sync).

Every number here comes from docs/plan/04-adaptive-model.md unless a comment in
model/README.md records it as an MVP decision.
"""

from __future__ import annotations

from typing import Final

ALPHA: Final = 0.1
ACC_WINDOW: Final = 20
RECENT_MAX: Final = 50
FOCUS_HISTORY_MAX: Final = 20
MAX_STREAK: Final = 3

# Focus spreading (README "Choosing the next exercise" decision; 04-adaptive-model.md).
FOCUS_CANDIDATES: Final = 3
FOCUS_FLOOR: Final = 0.1
SHARE_WINDOW: Final = 10
SHARE_MAX: Final = 4
LOW_WEIGHT: Final = 0.3
STARVE_WINDOW: Final = 12

MASTER_N: Final = 8
MASTER_ACC: Final = 0.9
MASTER_EFF: Final = 1.25
EFF_FLOOR: Final = 0.5

MIN_ACTIVE: Final = 4
MAX_ACTIVE: Final = 7

REVIEW_P: Final = 0.2
REVIEW_KEYS: Final = 1.5
REVIEW_TIME: Final = 1.3
REVIEW_FAIL_FACTOR: Final = 0.8
MAX_INTERVAL_DAYS: Final = 60
DAY: Final = 86400

COMPOSITE_P: Final = 0.2
COMPOSITE_CONF: Final = 0.8

PLACEMENT_ACTIVE_CONF: Final = 0.6
PLACEMENT_INFERRED_CONF: Final = 0.5
PLACEMENT_INFERRED_REVIEWS: Final = 2
PLACEMENT_FOUNDATION_TIER: Final = 3

IMPROVED_DELTA: Final = 0.1
PROJECTION_WINDOW: Final = 30
PROJECTION_AHEAD: Final = 30
PROJECTION_QUADRATIC_N: Final = 15
PROJECTION_MIN_N: Final = 3
PROJECTION_MIN_R2: Final = 0.5

DEFAULT_TARGET_BASE: Final = 1200
DEFAULT_PER_KEY: Final = 180


class Status:
    """Skill status values."""

    LOCKED: Final = "locked"
    ACTIVE: Final = "active"
    INTRODUCED: Final = "introduced"
    MASTERED: Final = "mastered"
    REVIEW: Final = "review"


IN_ROTATION: Final = (Status.ACTIVE, Status.INTRODUCED)
MASTERED_LIKE: Final = (Status.MASTERED, Status.REVIEW)
