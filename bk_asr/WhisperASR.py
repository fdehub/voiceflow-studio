import json
import logging
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import threading
import time
from typing import List, Optional, Union

import requests

from .ASRData import ASRDataSeg
from .BaseASR import BaseASR
from .ProxyPool import whisper_proxy_pool

DEFAULT_KEY = os.getenv("OPENAI_API_KEY", "")

# 全局轮询计数器与锁，支持多线程并发安全地轮换 Key 及单 Key 串行节流防封
_key_index = 0
_key_lock = threading.Lock()
_single_key_io_lock = threading.Lock()
_last_req_time = 0.0

HALLUCINATION_KEYWORDS = (
    "请不吝点赞",
    "明镜与点点栏目",
    "订阅 转发 打赏支持",
    "Amara.org",
    "字幕由Amara",
)


def _load_config():
    """在多个候选路径中查找并加载 whisper_config.json"""
    candidates = [
        Path(__file__).resolve().parent.parent / "whisper_config.json",
        Path(__file__).resolve().parent.parent.parent / "whisper_config.json",
        Path.cwd() / "whisper_config.json"
    ]
    for p in candidates:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logging.warning(f"读取 {p} 失败，尝试正则提取: {e}")
                # 容错：如果用户手写 JSON 有轻微语法错误，尝试用正则提取里面的 Key
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        text = f.read()
                    keys = re.findall(r'gsk_[A-Za-z0-9_-]+', text)
                    if keys:
                        return {
                            "api_key": keys,
                            "model": "whisper-large-v3-turbo",
                            "base_url": "https://api.groq.com/openai/v1"
                        }
                except Exception:
                    pass
    return {}


def _get_ffmpeg_path() -> str:
    """获取 ffmpeg 可执行程序路径"""
    local_ffmpeg = Path(__file__).resolve().parent.parent / "ffmpeg.exe"
    if not local_ffmpeg.exists():
        local_ffmpeg = Path(__file__).resolve().parent.parent.parent / "ffmpeg.exe"
    if local_ffmpeg.exists():
        return str(local_ffmpeg)
    return "ffmpeg"


class WhisperASR(BaseASR):
    def __init__(self, audio_path: Union[str, bytes], model: str = None, use_cache: bool = False,
                 base_url: str = None, api_key: Union[str, List[str]] = None):
        super().__init__(audio_path, use_cache)

        cfg = _load_config()
        config_key = cfg.get("api_key")
        config_url = cfg.get("base_url")
        config_model = cfg.get("model")
        self.proxy = cfg.get("proxy")

        # 整理所有的 api_keys
        raw_keys = api_key or os.getenv('OPENAI_API_KEY') or config_key or DEFAULT_KEY
        if isinstance(raw_keys, list):
            self.api_keys = [str(k).strip() for k in raw_keys if str(k).strip()]
        elif isinstance(raw_keys, str):
            parts = [k.strip() for k in re.split(r'[,;\n\r]+', raw_keys) if k.strip()]
            self.api_keys = parts if parts else [raw_keys.strip()]
        else:
            self.api_keys = [DEFAULT_KEY]

        if not self.api_keys:
            raise ValueError("Whisper 需要配置 OPENAI_API_KEY 环境变量或在 whisper_config.json 中配置 api_key")

        # 根据第一个 Key 自动识别类型
        first_key = self.api_keys[0]
        if first_key.startswith("gsk_"):
            self.base_url = base_url or os.getenv('OPENAI_BASE_URL') or config_url or "https://api.groq.com/openai/v1"
            self.model = model or os.getenv('WHISPER_MODEL') or config_model or "whisper-large-v3-turbo"
        else:
            self.base_url = base_url or os.getenv('OPENAI_BASE_URL') or config_url or "https://api.openai.com/v1"
            self.model = model or os.getenv('WHISPER_MODEL') or config_model or "whisper-1"

    def _run(self, callback=None) -> dict:
        return self._submit(callback=callback)

    def _make_segments(self, resp_data: dict) -> list[ASRDataSeg]:
        segments = []
        for u in resp_data.get('segments', []):
            text = u.get('text', '').strip()
            if not text:
                continue
            if any(kw in text for kw in HALLUCINATION_KEYWORDS):
                continue
            start_ms = int(float(u.get('start', 0.0)) * 1000)
            end_ms = int(float(u.get('end', 0.0)) * 1000)
            segments.append(ASRDataSeg(text, start_ms, end_ms))
        return segments

    def _get_key(self) -> str:
        return f"{self.__class__.__name__}-{self.model}-{self.crc32_hex}"

    def _get_duration(self, audio_file: str) -> float:
        """获取音频文件的时长(秒)"""
        ffmpeg_exe = _get_ffmpeg_path()
        kwargs = {'capture_output': True, 'text': True, 'errors': 'ignore'}
        if platform.system() == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs['startupinfo'] = startupinfo
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

        p = subprocess.run([ffmpeg_exe, '-i', audio_file], **kwargs)
        m = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.?\d*)', p.stderr)
        if m:
            h, mins, s = m.groups()
            return int(h) * 3600 + int(mins) * 60 + float(s)
        return 0.0

    def _slice_chunk(self, audio_file: str, start_sec: float, dur_sec: float, output_path: str):
        """利用 ffmpeg 静默切分指定区间的音频块（MP3 优先使用流拷贝提速）"""
        ffmpeg_exe = _get_ffmpeg_path()
        kwargs = {'capture_output': True, 'check': True}
        if platform.system() == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs['startupinfo'] = startupinfo
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

        if str(audio_file).lower().endswith('.mp3'):
            fast_cmd = [
                ffmpeg_exe,
                '-ss', str(start_sec),
                '-t', str(dur_sec),
                '-i', audio_file,
                '-vn', '-c:a', 'copy',
                '-f', 'mp3',
                '-y',
                output_path
            ]
            try:
                subprocess.run(fast_cmd, **kwargs)
                if os.path.exists(output_path):
                    sz = os.path.getsize(output_path)
                    if 1024 < sz <= 20 * 1024 * 1024:
                        return
            except Exception:
                pass

        cmd = [
            ffmpeg_exe,
            '-ss', str(start_sec),
            '-t', str(dur_sec),
            '-i', audio_file,
            '-vn', '-ar', '16000', '-ac', '1', '-b:a', '48k',
            '-f', 'mp3',
            '-y',
            output_path
        ]
        subprocess.run(cmd, **kwargs)

    @staticmethod
    def _parse_retry_wait_seconds(resp) -> float:
        """从 429 响应头或响应正文中解析需要等待的冷却秒数"""
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after) + 1.5
            except ValueError:
                pass
        text = resp.text or ""
        m = re.search(r'try again in\s*(?:(\d+)h)?(?:(\d+)m)?(\d+(?:\.\d+)?)s', text, re.IGNORECASE)
        if m:
            h = int(m.group(1) or 0)
            mins = int(m.group(2) or 0)
            sec = float(m.group(3) or 0.0)
            return h * 3600 + mins * 60 + sec + 2.0
        m_min = re.search(r'try again in\s*(\d+)m', text, re.IGNORECASE)
        if m_min:
            return int(m_min.group(1)) * 60 + 5.0
        return 15.0

    def _submit_audio_bytes(self, audio_bytes: bytes, desc: str = "", callback=None) -> dict:
        """提交单个音频块：单 Key 模式下强制排队慢发+自动冷却重试；多 Key 模式下轮询容灾"""
        global _key_index, _last_req_time

        url = self.base_url.rstrip('/') + "/audio/transcriptions"
        files = {
            "file": ("audio.mp3", audio_bytes, "audio/mpeg")
        }
        data = {
            "model": self.model,
            "response_format": "verbose_json",
            "language": "zh",
            "temperature": "0"
        }

        is_single_key = (len(self.api_keys) == 1)
        max_attempts = 5 if is_single_key else max(5, len(self.api_keys) * 2)

        with _key_lock:
            start_idx = _key_index % len(self.api_keys)
            _key_index = (_key_index + 1) % len(self.api_keys)

        last_error = None
        for attempt in range(max_attempts):
            current_key_idx = (start_idx + attempt) % len(self.api_keys)
            current_key = self.api_keys[current_key_idx]
            masked_key = current_key[:8] + "..." + current_key[-4:] if len(current_key) > 12 else current_key
            headers = {
                "Authorization": f"Bearer {current_key}"
            }

            # 动态获取 Whisper 代理节点
            raw_px = None
            proxies = None
            pool_res = whisper_proxy_pool.get_proxy()
            if pool_res:
                raw_px, proxies = pool_res
            elif self.proxy:
                p = str(self.proxy).strip()
                if p.lower().startswith("socks5://"):
                    p = "socks5h://" + p[len("socks5://"):]
                proxies = {"http": p, "https": p}
            else:
                import urllib.request
                sys_proxies = urllib.request.getproxies()
                if sys_proxies.get("http") or sys_proxies.get("https"):
                    proxies = sys_proxies

            try:
                chunk_info = f" ({desc})" if desc else ""
                if is_single_key:
                    # 单 Key 串行节流锁：避免多任务同时轰炸同一个 Key 导致封号或突发 429
                    with _single_key_io_lock:
                        elapsed = time.time() - _last_req_time
                        if elapsed < 2.5:
                            time.sleep(2.5 - elapsed)
                        logging.info(f"使用单 Key [{masked_key}]{chunk_info} 发起识别请求 (尝试 {attempt + 1}/{max_attempts})...")
                        resp = requests.post(url, headers=headers, files=files, data=data, timeout=180, proxies=proxies)
                        _last_req_time = time.time()
                else:
                    logging.info(f"使用 Key [{masked_key}]{chunk_info} 发起识别请求 (尝试 {attempt + 1}/{max_attempts})...")
                    resp = requests.post(url, headers=headers, files=files, data=data, timeout=180, proxies=proxies)

                if resp.status_code == 200:
                    if raw_px:
                        whisper_proxy_pool.report_result(raw_px, success=True)
                    return resp.json()

                if raw_px and resp.status_code in (502, 503, 504):
                    whisper_proxy_pool.report_result(raw_px, success=False)

                err_msg = f"Key [{masked_key}] 请求失败 (HTTP {resp.status_code}): {resp.text}"
                logging.warning(err_msg)
                last_error = err_msg

                # 处理账号封禁/限制
                if "restricted" in resp.text.lower() or resp.status_code in (401, 403):
                    if not is_single_key and attempt < max_attempts - 1:
                        logging.info("当前 Key 不可用，切换下一个 Key 重试...")
                        continue
                    raise RuntimeError(f"API Key 不可用或已被限制: {resp.text}")

                # 处理 429 速率/配额限制
                if resp.status_code == 429:
                    wait_s = self._parse_retry_wait_seconds(resp)
                    if is_single_key:
                        if wait_s <= 180 and attempt < max_attempts - 1:
                            wait_int = int(math.ceil(wait_s))
                            logging.info(f"触发短时频率保护，自动等待 {wait_int} 秒后继续{chunk_info}...")
                            if callback:
                                callback(None, f"配额短时冷却 {wait_int} 秒后自动继续 {desc}...")
                            with _single_key_io_lock:
                                time.sleep(wait_s)
                                _last_req_time = time.time()
                            continue
                        else:
                            wait_min = max(1, int(math.ceil(wait_s / 60.0)))
                            raise RuntimeError(
                                f"当前 Key 本小时配额已跑满（需冷却约 {wait_min} 分钟）。"
                                f"前面已跑完的分块已全部自动存档，冷却后重新开始将直接从当前断点继续，绝不浪费配额！"
                            )
                    else:
                        if attempt < max_attempts - 1:
                            time.sleep(2.0)
                            continue
                        raise RuntimeError(err_msg)

                # 处理服务端 5xx 抖动
                if resp.status_code in (500, 502, 503, 504) and attempt < max_attempts - 1:
                    backoff = 4 * (attempt + 1)
                    logging.info(f"云端接口短暂繁忙 (HTTP {resp.status_code})，等待 {backoff} 秒后重试...")
                    time.sleep(backoff)
                    continue

                raise RuntimeError(err_msg)

            except (requests.exceptions.SSLError, requests.exceptions.ProxyError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if raw_px:
                    whisper_proxy_pool.report_result(raw_px, success=False)
                friendly_msg = (
                    f"连接 Groq 云端接口网络抖动或中断（前面已完成的分块均已自动保存，可直接重试续传）。\n"
                    f"底层错误: {e}"
                )
                last_error = friendly_msg
                logging.warning(f"Key [{masked_key}] 网络异常 (尝试 {attempt + 1}/{max_attempts}): {e}")
                if attempt < max_attempts - 1:
                    backoff = 4 * (attempt + 1)
                    if callback:
                        callback(None, f"网络波动，{backoff}秒后自动重试 {desc}...")
                    time.sleep(backoff)
                    continue
                raise RuntimeError(friendly_msg)
            except requests.exceptions.RequestException as e:
                if raw_px:
                    whisper_proxy_pool.report_result(raw_px, success=False)
                last_error = f"Key [{masked_key}] 请求异常: {e}"
                logging.warning(last_error)
                if attempt < max_attempts - 1:
                    time.sleep(3 * (attempt + 1))
                    continue
                raise RuntimeError(last_error)

        raise RuntimeError(f"转录请求多次重试仍未成功，已完成分块已保存，最后一次错误: {last_error}")

    def _submit(self, callback=None) -> dict:
        """智能提交：小文件直接提交，超长音频自动分块切片转录并支持逐块断点续传"""
        file_size_mb = len(self.file_binary) / (1024 * 1024)

        # 小于等于 20MB 的音频，直接单次提交
        if file_size_mb <= 20.0:
            if callback:
                callback(20, f"正在提交 {self.model} 云端转录...")
            res = self._submit_audio_bytes(self.file_binary, callback=callback)
            if callback:
                callback(100, "转录完成")
            return res

        # 超过 20MB（大音频/长视频）：自动分块转录 + 逐块断点缓存
        logging.info(f"检测到超大音频 ({file_size_mb:.1f} MB)，启动自动分块断点续传流程...")

        temp_source = None
        source_file = None
        if isinstance(self.audio_path, str) and os.path.exists(self.audio_path):
            source_file = self.audio_path
        else:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
                tf.write(self.file_binary)
                temp_source = tf.name
                source_file = tf.name

        try:
            total_duration = self._get_duration(source_file)
            if total_duration <= 0:
                return self._submit_audio_bytes(self.file_binary, callback=callback)

            # 每 10 分钟 (600秒) 切一个分块，单块大小仅约 3.6MB，极其稳定
            chunk_len = 600.0
            total_chunks = int(math.ceil(total_duration / chunk_len))
            logging.info(f"总时长 {int(total_duration)} 秒 ({total_duration/60:.1f} 分钟)，自动切分为 {total_chunks} 个分块...")

            base_key = self._get_key()
            all_segments = []
            full_text = []

            for i in range(total_chunks):
                start_sec = i * chunk_len
                dur_sec = min(chunk_len, total_duration - start_sec)
                start_m = int(start_sec // 60)
                end_m = int((start_sec + dur_sec) // 60)
                chunk_desc = f"分块 {i+1}/{total_chunks} [{start_m}m~{end_m}m]"
                chunk_key = f"{base_key}-chunk-{i}"
                percent = int(10 + (i / total_chunks) * 85)

                # 检查该 10 分钟分块是否已有本地缓存（跑完一段存一段，断点零损耗续传）
                cached_chunk = self.cache.get(chunk_key) if self.use_cache else None
                if isinstance(cached_chunk, dict) and "segments" in cached_chunk:
                    logging.info(f"命中分块断点缓存 {chunk_desc}，直接复用（零配额消耗）")
                    if callback:
                        callback(percent, f"已复用缓存 {chunk_desc}")
                    chunk_segments = cached_chunk.get("segments", [])
                else:
                    if callback:
                        callback(percent, f"正在转录 {chunk_desc}...")

                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as chunk_f:
                        chunk_path = chunk_f.name

                    try:
                        self._slice_chunk(source_file, start_sec, dur_sec, chunk_path)
                        with open(chunk_path, "rb") as cf:
                            chunk_bytes = cf.read()

                        chunk_resp = self._submit_audio_bytes(chunk_bytes, desc=chunk_desc, callback=callback)
                        # 仅保留核心时间轴与文本字段，大幅缩减缓存体积
                        chunk_segments = [
                            {
                                "start": float(s.get("start", 0.0)),
                                "end": float(s.get("end", 0.0)),
                                "text": str(s.get("text", "")).strip()
                            }
                            for s in chunk_resp.get("segments", [])
                            if str(s.get("text", "")).strip()
                        ]
                        if self.use_cache:
                            self.cache[chunk_key] = {"segments": chunk_segments}
                            self._save_cache()
                    finally:
                        if os.path.exists(chunk_path):
                            try:
                                os.remove(chunk_path)
                            except Exception:
                                pass

                # 偏移该分块内所有字幕段的时间戳（构建新字典避免污染缓存对象）
                for seg in chunk_segments:
                    seg_text = str(seg.get("text", "")).strip()
                    if not seg_text or any(kw in seg_text for kw in HALLUCINATION_KEYWORDS):
                        continue
                    all_segments.append({
                        "start": float(seg.get("start", 0.0)) + start_sec,
                        "end": float(seg.get("end", 0.0)) + start_sec,
                        "text": seg_text
                    })
                    full_text.append(seg_text)

            # 全部分块组装完成后，清理临时分块键（最终完整结果由 BaseASR.run 统一存入 base_key）
            if self.use_cache:
                for i in range(total_chunks):
                    self.cache.pop(f"{base_key}-chunk-{i}", None)

            if callback:
                callback(100, "转录完成")

            return {
                "task": "transcribe",
                "language": "Chinese",
                "duration": total_duration,
                "segments": all_segments,
                "text": " ".join(full_text)
            }
        finally:
            if temp_source and os.path.exists(temp_source):
                try:
                    os.remove(temp_source)
                except Exception:
                    pass

