from apps.core.exceptions import BusinessRuleError

MODULE_LABELS = {
    "affirmations": "Affirmations",
    "reading": "Reading",
    "fitness": "Fitness",
    "hydration": "Hydration",
    "sleep": "Sleep",
    "journal": "Journal",
    "goals": "Goals",
    "mindfulness": "Mindfulness",
    "admin": "Personal admin",
}


def require_module(user, key: str) -> None:
    """Optional-module gate for write endpoints. Data is never deleted when a module is turned off."""
    if not user.preferences.module_enabled(key):
        raise BusinessRuleError(
            f"The {MODULE_LABELS.get(key, key)} module is turned off. You can turn it on in Settings → Modules.",
            code="module_disabled",
            status_code=403,
        )
