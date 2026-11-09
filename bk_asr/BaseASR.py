import json
import logging
import os
import zlib
import tempfile
import threading

from .ASRData import ASRDataSeg, ASRData


class BaseASR:
    SUPPORTED_SOUND_FORMAT = ["flac", "m4a", "mp3", "wav"]
    CACHE_FILE = os.path.join(tempfile.gettempdir(), "bk_asr", "asr_cache.json")
    _lock = threading.Lock()

    def __init__(self, audio_path: [str, bytes], use_cache: bool = False):
        self.audio_path = audio_path
        self.file_binary = None

        self.crc32_hex = None
        self.use_cache = use_cache

        self._set_data()

        self.cache = self._load_cache()

    def _load_cache(self):
        if not self.use_cache:
            return {}
        os.makedirs(os.path.dirname(self.CACHE_FILE), exist_ok=True)
        with self._lock:
            if os.path.exists(self.CACHE_FILE):
                try:
                    with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                        cache = json.load(f)
                        if isinstance(cache, dict):
                            return cache
                except (json.JSONDecodeError, IOError):
                    return {}
            return {}

    def _save_cache(self):
        if not self.use_cache:
            return
        with self._lock:
            try:
                disk_cache = {}
                if os.path.exists(self.CACHE_FILE):
                    try:
                        with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                            c = json.load(f)
                            if isinstance(c, dict):
                                disk_cache = c
                    except Exception:
                        pass
                disk_cache.update(self.cache)
                # 当缓存条目过多导致体积超大时，仅淘汰最早的一批完整历史缓存，绝不误删正在断点续传的 -chunk- 分块
                if len(disk_cache) > 60:
                    full_keys = [k for k in disk_cache.keys() if "-chunk-" not in k]
                    for old_k in full_keys[:-40]:
                        disk_cache.pop(old_k, None)
                self.cache = disk_cache
                with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.cache, f, ensure_ascii=False)
            except IOError as e:
                logging.error(f"Failed to save cache: {e}")

    def _set_data(self):
        if isinstance(self.audio_path, bytes):
            self.file_binary = self.audio_path
        else:
            ext = self.audio_path.split(".")[-1].lower()
            assert ext in self.SUPPORTED_SOUND_FORMAT, f"Unsupported sound format: {ext}"
            assert os.path.exists(self.audio_path), f"File not found: {self.audio_path}"
            with open(self.audio_path, "rb") as f:
                self.file_binary = f.read()
        crc32_value = zlib.crc32(self.file_binary) & 0xFFFFFFFF
        self.crc32_hex = format(crc32_value, '08x')

    def _get_key(self):
        return f"{self.__class__.__name__}-{self.crc32_hex}"

    def run(self, callback=None):
        k = self._get_key()
        resp_data = None
        if k in self.cache and self.use_cache:
            cached = self.cache[k]
            if isinstance(cached, dict) and ('data' in cached or 'result' in cached or 'segments' in cached):
                resp_data = cached
            else:
                self.cache.pop(k, None)
                self._save_cache()

        if resp_data is None:
            resp_data = self._run(callback=callback)
            if isinstance(resp_data, dict) and ('data' in resp_data or 'result' in resp_data or 'segments' in resp_data):
                self.cache[k] = resp_data
                self._save_cache()

        segments = self._make_segments(resp_data)
        return ASRData(segments)

    def _make_segments(self, resp_data: dict) -> list[ASRDataSeg]:
        raise NotImplementedError("_make_segments method must be implemented in subclass")

    def _run(self, callback=None) -> dict:
        """ Run the ASR service and return the response data. """
        raise NotImplementedError("_run method must be implemented in subclass")



