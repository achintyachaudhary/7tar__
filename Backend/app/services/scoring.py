"""Stock overall scoring (0–10) combining technical score and holding quality."""


def compute_overall_score(
    technical_score: int | float,
    retail_pct: float | None = None,
) -> float:
    """
    Map the technical score (0–10 scale, max raw score ~10 from indicators)
    to a base 0–8 and apply a retail-holding penalty.

    Retail penalty (retail = public - institutional, i.e. retail & others %):
      > 75 %  → -3
      > 65 %  → -2
      > 50 %  → -1
      ≤ 50 %  →  0

    Final score clamped to [0, 10].
    """
    MAX_TECH = 10.0
    base = min(float(technical_score) / MAX_TECH * 8.0, 8.0)

    penalty = 0.0
    if retail_pct is not None:
        if retail_pct > 75:
            penalty = 3.0
        elif retail_pct > 65:
            penalty = 2.0
        elif retail_pct > 50:
            penalty = 1.0

    raw = base - penalty
    return round(max(min(raw, 10.0), 0.0), 1)
