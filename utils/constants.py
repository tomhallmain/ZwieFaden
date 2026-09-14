from enum import IntEnum


class AppMode(IntEnum):
    """Application mode; value is the QStackedWidget index."""
    JOIN = 0
    DIFF = 1

    @staticmethod
    def get(value, default: "AppMode" = None) -> "AppMode":
        """Resolve a cached value (int or name) to AppMode, or return default on failure."""
        if default is None:
            default = AppMode.DIFF
        try:
            if isinstance(value, int):
                return AppMode(value)
            return AppMode[value]
        except (ValueError, KeyError):
            return default


class AppInfo:
    SERVICE_NAME = "MyPersonalApplicationsService"
    APP_IDENTIFIER = "ZwieFaden"
    # Identifiers this app has previously been filed under. Key material
    # stays filed under the name in force when it was written, so a rename
    # must list the old name here until everything encrypted under it has
    # been migrated. Empty: this app has not been renamed.
    LEGACY_APP_IDENTIFIERS = []
