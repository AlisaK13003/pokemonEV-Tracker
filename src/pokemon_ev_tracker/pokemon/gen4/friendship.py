"""Generation IV friendship display helpers."""

MAX_FRIENDSHIP = 255


def friendship_label(value: int) -> str:
    if not 0 <= value <= MAX_FRIENDSHIP:
        raise ValueError("Friendship must be between 0 and 255.")
    if value == MAX_FRIENDSHIP:
        return "Max"
    if value >= 200:
        return "Very High"
    if value >= 150:
        return "High"
    if value >= 100:
        return "Neutral"
    if value >= 50:
        return "Low"
    return "Very Low"
