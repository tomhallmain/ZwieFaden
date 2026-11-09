import hashlib
import json
import os
import shutil

# from lib.position_data import PositionData
from utils.constants import AppInfo
from utils.encryptor import encrypt_data_to_file, decrypt_data_from_file
from utils.logging_setup import get_logger
from utils.translations import _

logger = get_logger("app_info_cache")

class AppInfoCache:
    CACHE_LOC = os.path.join(os.path.dirname(os.path.abspath(os.path.dirname(__file__))), "app_info_cache.enc")
    JSON_LOC = os.path.join(os.path.dirname(os.path.abspath(os.path.dirname(__file__))), "app_info_cache.json")
    INFO_KEY = "info"
    HISTORY_KEY = "run_history"
    MAX_HISTORY_ENTRIES = 1000
    NUM_BACKUPS = 4  # Number of backup files to maintain

    def __init__(self):
        self._cache = {
            AppInfoCache.INFO_KEY: {},
        }
        _override = os.environ.get("ZWIEFADEN_CACHE_DIR")
        self.cache_loc = os.path.join(_override, "app_info_cache.enc") if _override else AppInfoCache.CACHE_LOC
        self.json_loc = os.path.join(_override, "app_info_cache.json") if _override else AppInfoCache.JSON_LOC
        self.load()
        self.validate()

    def wipe_instance(self):
        self._cache = {
            AppInfoCache.INFO_KEY: {},
        }

    def store(self):
        try:
            cache_data = json.dumps(self._cache).encode('utf-8')
            encrypt_data_to_file(
                cache_data,
                AppInfo.SERVICE_NAME,
                AppInfo.APP_IDENTIFIER,
                self.cache_loc
            )
        except Exception as e:
            logger.error(_("Error storing cache: {0}").format(e))
            raise e

    def _try_load_cache_from_file(self, path):
        """Attempt to load and decrypt the cache from the given file path. Raises on failure."""
        encrypted_data = decrypt_data_from_file(
            path,
            AppInfo.SERVICE_NAME,
            AppInfo.APP_IDENTIFIER
        )
        return json.loads(encrypted_data.decode('utf-8'))

    def load(self):
        try:
            if os.path.exists(self.json_loc):
                logger.info(_("Removing old cache file: {0}").format(self.json_loc))
                # Get the old data first
                with open(self.json_loc, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
                self.store() # store encrypted cache
                os.remove(self.json_loc)
                return

            # Try encrypted cache and backups in order
            cache_paths = [self.cache_loc] + self._get_backup_paths()
            any_exist = any(os.path.exists(path) for path in cache_paths)
            if not any_exist:
                logger.info(_("No cache file found at {0}, creating new cache").format(self.cache_loc))
                return

            for path in cache_paths:
                if os.path.exists(path):
                    try:
                        self._cache = self._try_load_cache_from_file(path)
                        # Only shift backups if we loaded from the main file
                        if path == self.cache_loc:
                            message = _("Loaded cache from {0}").format(self.cache_loc)
                            rotated_count = self._rotate_backups()
                            if rotated_count > 0:
                                message += _(", rotated {0} backups").format(rotated_count)
                            logger.info(message)
                        else:
                            logger.warning(_("Loaded cache from backup: {0}").format(path))
                        return
                    except Exception as e:
                        logger.error(_("Failed to load cache from {0}: {1}").format(path, e))
                        continue
            # If we get here, all attempts failed (but at least one file existed)
            raise Exception(f"Failed to load cache from all locations: {cache_paths}")
        except Exception as e:
            logger.error(_("Error loading cache: {0}").format(e))
            pass

    def validate(self):
        pass

    def set(self, key, value):
        if AppInfoCache.INFO_KEY not in self._cache:
            self._cache[AppInfoCache.INFO_KEY] = {}
        self._cache[AppInfoCache.INFO_KEY][key] = value

    def get(self, key, default_val=None):
        if AppInfoCache.INFO_KEY not in self._cache or key not in self._cache[AppInfoCache.INFO_KEY]:
            return default_val
        return self._cache[AppInfoCache.INFO_KEY][key]

    # def set_display_position(self, master):
    #     """Store the main window's display position and size."""
    #     self.set("display_position", PositionData.from_master(master).to_dict())

    # def set_virtual_screen_info(self, master):
    #     """Store the virtual screen information."""
    #     try:
    #         self.set("virtual_screen_info", PositionData.from_master_virtual_screen(master).to_dict())
    #     except Exception as e:
    #         logger.warning(f"Failed to store virtual screen info: {e}")

    # def get_virtual_screen_info(self):
    #     """Get the cached virtual screen info, returns None if not set or invalid."""
    #     virtual_screen_data = self.get("virtual_screen_info")
    #     if not virtual_screen_data:
    #         return None
    #     return PositionData.from_dict(virtual_screen_data)

    # def get_display_position(self):
    #     """Get the cached display position, returns None if not set or invalid."""
    #     position_data = self.get("display_position")
    #     if not position_data:
    #         return None
    #     return PositionData.from_dict(position_data)

    def export_as_json(self, json_path=None):
        """Export the current cache as a JSON file (not encrypted)."""
        if json_path is None:
            json_path = self.json_loc
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)
        return json_path

    def _get_backup_paths(self):
        """Get list of backup file paths in order of preference"""
        backup_paths = []
        for i in range(1, self.NUM_BACKUPS + 1):
            index = "" if i == 1 else f"{i}"
            path = f"{self.cache_loc}.bak{index}"
            backup_paths.append(path)
        return backup_paths

    def _rotate_backups(self):
        """Rotate backup files: move each backup to the next position, oldest gets overwritten"""
        backup_paths = self._get_backup_paths()
        rotated_count = 0
        
        # Remove the oldest backup if it exists
        if os.path.exists(backup_paths[-1]):
            os.remove(backup_paths[-1])
        
        # Shift backups: move each backup to the next position
        for i in range(len(backup_paths) - 1, 0, -1):
            if os.path.exists(backup_paths[i - 1]):
                shutil.copy2(backup_paths[i - 1], backup_paths[i])
                rotated_count += 1
        
        # Copy main cache to first backup position
        shutil.copy2(self.cache_loc, backup_paths[0])
        
        return rotated_count


app_info_cache = AppInfoCache()
