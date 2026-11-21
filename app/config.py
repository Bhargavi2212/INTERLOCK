"""Settings from environment variables (names in .env.example).

Nothing is checked at import, so tests and the container start without a .env.
A required setting is checked when it is first used; the error names the
variable, never its value. Secret values never appear in repr, str or logs.
"""

import os
from functools import lru_cache

SECRET_NAMES = ("GEMINI_API_KEY", "ACCESS_CODE")

SETTING_NAMES = (
    "GEMINI_API_KEY",
    "MODEL_HYDROGEN",
    "MODEL_ARGON",
    "MODEL_CARBON",
    "MODEL_NEON",
    "MODEL_DECISIONS",
    "MANAGED_AGENT",
    "GCP_PROJECT",
    "GCP_REGION",
    "GCS_BUCKET",
    "FIRESTORE_DATABASE",
    "ACCESS_CODE",
    "APP_VERSION",
    "STORE",
)

DEFAULTS = {
    "GCP_REGION": "us-central1",
    "FIRESTORE_DATABASE": "(default)",
    "APP_VERSION": "dev",
    "STORE": "gcp",
}


class MissingSetting(RuntimeError):
    """A required environment variable is not set."""


class Settings:
    def __init__(self, env=None):
        env = os.environ if env is None else env
        self._values = {}
        for name in SETTING_NAMES:
            value = (env.get(name) or "").strip()
            self._values[name] = value or DEFAULTS.get(name, "")

    def get(self, name: str) -> str:
        """Value of a setting, or "" when unset."""
        if name not in self._values:
            raise KeyError(f"unknown setting {name}")
        return self._values[name]

    def require(self, name: str) -> str:
        """Value of a setting; raises MissingSetting naming it when unset."""
        value = self.get(name)
        if not value:
            raise MissingSetting(f"{name} is not set")
        return value

    @property
    def app_version(self) -> str:
        return self._values["APP_VERSION"]

    def __repr__(self) -> str:
        shown = []
        for name in SETTING_NAMES:
            value = self._values[name]
            if name in SECRET_NAMES:
                shown.append(f"{name}={'***' if value else '<unset>'}")
            else:
                shown.append(f"{name}={value or '<unset>'}")
        return f"Settings({', '.join(shown)})"

    __str__ = __repr__


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def get_access_code() -> str:
    """The shared access code, or "" when unset (protected routes then answer 503)."""
    return get_settings().get("ACCESS_CODE")
