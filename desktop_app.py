import concurrent.futures
import json
import logging
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import threading
import time
import webbrowser
from typing import Dict, List, Optional

# 确保在嵌入式运行时下也能正确重定向输出
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

# 加入当前目录到 sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 设置 Windows AppUserModelID，使任务栏/状态栏脱离 Python 默认分组并显示软件专属图标
if platform.system() == 'Windows':
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('fdehub.voiceflow.desktop.v1')
    except Exception:
        pass

# 确保运行时目录在 PATH 中，以便 pythonnet/.NET CLR 能正确加载 python310.dll
runtime_dir = os.path.dirname(sys.executable)
if runtime_dir:
    os.environ['PATH'] = runtime_dir + ';' + os.environ.get('PATH', '')
    if hasattr(os, 'add_dll_directory') and os.path.isdir(runtime_dir):
        try:
            os.add_dll_directory(runtime_dir)
        except Exception:
            pass


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("AsrDesktop")

import webview

try:
    from bk_asr.BcutASR import BcutASR
    from bk_asr.JianYingASR import JianYingASR
    from bk_asr.WhisperASR import WhisperASR
    from bk_asr.ASRData import from_subtitle_file
    from bk_asr.ProxyPool import bcut_proxy_pool, BcutProxyPool, whisper_proxy_pool, WhisperProxyPool, normalize_proxy
except (ImportError, ValueError) as e:
    logger.error(f"导入 ASR 模块失败: {e}")


def get_ffmpeg_path() -> str:
    local_ffmpeg = Path(current_dir) / "ffmpeg.exe"
    if local_ffmpeg.is_file():
        return str(local_ffmpeg)
    parent_ffmpeg = Path(current_dir).parent / "ffmpeg.exe"
    if parent_ffmpeg.is_file():
        return str(parent_ffmpeg)
    return "ffmpeg"


def video2audio(input_file: str, output: str = "") -> bool:
    """使用 ffmpeg 将视频/音频转换为 16kHz 单声道 48k CBR mp3"""
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = get_ffmpeg_path()

    cmd = [
        ffmpeg_exe,
        '-i', input_file,
        '-vn',
        '-ar', '16000',
        '-ac', '1',
        '-b:a', '48k',
        '-f', 'mp3',
        '-af', 'aresample=async=1',
        '-y',
        str(output_path)
    ]
    kwargs = {
        'capture_output': True,
        'check': True,
        'encoding': 'utf-8',
        'errors': 'replace'
    }
    if platform.system() == 'Windows':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs['startupinfo'] = startupinfo
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

    result = subprocess.run(cmd, **kwargs)
    return result.returncode == 0 and output_path.is_file()


class DesktopApi:
    """供前端调用的核心 API"""

    def __init__(self):
        self._window: Optional[webview.Window] = None
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        self._active_tasks: Dict[str, bool] = {}
        self._lock = threading.Lock()

    def set_window(self, window: webview.Window):
        self._window = window

    def emit_event(self, event_name: str, data: dict):
        """向前端发送实时状态事件"""
        if not self._window:
            return
        payload = json.dumps(data, ensure_ascii=False)
        js = f"window.__onDesktopEvent && window.__onDesktopEvent({json.dumps(event_name)}, {payload});"
        try:
            self._window.evaluate_js(js)
        except Exception as e:
            logger.debug(f"向前端发送事件失败: {e}")

    # ─────────────────────────────────────────────────────────────
    # 文件选取与探测
    # ─────────────────────────────────────────────────────────────
    def select_files(self) -> List[dict]:
        """呼起原生多选文件对话框"""
        if not self._window:
            return []
        file_types = (
            '音视频文件 (*.mp4;*.mkv;*.avi;*.mov;*.flv;*.wmv;*.ts;*.webm;*.mp3;*.wav;*.m4a;*.flac;*.aac;*.ogg;*.wma)',
            '所有文件 (*.*)'
        )
        res = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=file_types
        )
        if not res:
            return []
        items = []
        for p in res:
            info = self._get_file_info(p)
            if info:
                items.append(info)
        return items

    def select_folder(self) -> List[dict]:
        """呼起原生选择文件夹对话框，递归扫描音视频文件"""
        if not self._window:
            return []
        res = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not res:
            return []
        folder_path = res[0] if isinstance(res, (list, tuple)) else res
        if not folder_path or not os.path.isdir(folder_path):
            return []

        video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.ts', '.webm', '.m4v'}
        media_exts = video_exts | {'.mp3', '.wav', '.m4a', '.flac', '.aac', '.ogg', '.wma', '.m4s', '.opus'}
        items = []
        for root, _, files in os.walk(folder_path):
            sorted_files = sorted(files, key=lambda s: [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)])
            for f in sorted_files:
                base, ext = os.path.splitext(f)
                ext = ext.lower()
                if ext in media_exts:
                    # 若同目录下存在同名视频文件，跳过转换残留的临时 .mp3
                    if ext == '.mp3' and any(os.path.exists(os.path.join(root, base + vext)) for vext in video_exts):
                        continue
                    full_path = os.path.join(root, f)
                    info = self._get_file_info(full_path)
                    if info:
                        items.append(info)
        return items

    def resolve_dropped_paths(self, paths: List[str]) -> List[dict]:
        """解析拖拽注入的路径列表（支持混合文件和文件夹并自动去重）"""
        video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.ts', '.webm', '.m4v'}
        media_exts = video_exts | {'.mp3', '.wav', '.m4a', '.flac', '.aac', '.ogg', '.wma', '.m4s', '.opus'}
        items = []
        seen_paths = set()

        def _add_file(file_path):
            norm = os.path.normpath(os.path.abspath(file_path))
            if norm not in seen_paths:
                info = self._get_file_info(norm)
                if info:
                    seen_paths.add(norm)
                    items.append(info)

        for p in paths:
            if not p or not os.path.exists(p):
                continue
            if os.path.isfile(p):
                ext = os.path.splitext(p)[1].lower()
                if ext in media_exts:
                    _add_file(p)
            elif os.path.isdir(p):
                for root, _, files in os.walk(p):
                    sorted_files = sorted(files, key=lambda s: [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)])
                    for f in sorted_files:
                        base, ext = os.path.splitext(f)
                        ext = ext.lower()
                        if ext in media_exts:
                            if ext == '.mp3' and any(os.path.exists(os.path.join(root, base + vext)) for vext in video_exts):
                                continue
                            full_path = os.path.join(root, f)
                            _add_file(full_path)
        return items

    def resolve_dropped_files(self, file_metas: List[dict]) -> List[dict]:
        """根据前端拖拽事件提取的元信息（包含绝对路径或文件名+大小）解析出真实文件对象。"""
        if not file_metas:
            return []

        resolved_paths = []
        unmatched_metas = []

        # 1. 优先使用已带完整路径的项（如某些环境支持 file.path 或 pywebviewFullPath）
        for item in file_metas:
            if not isinstance(item, dict):
                continue
            path = item.get("path") or item.get("pywebviewFullPath")
            if path and os.path.exists(path):
                resolved_paths.append(os.path.abspath(path))
            else:
                unmatched_metas.append(item)

        # 2. 如果存在未匹配项，通过系统环境寻找源目录
        if unmatched_metas:
            candidate_dirs = []

            # 2.1 从所有打开的资源管理器窗口中获取当前浏览目录与选中的文件
            try:
                import win32com.client
                shell = win32com.client.Dispatch("Shell.Application")
                for w in shell.Windows():
                    try:
                        for sel in w.Document.SelectedItems():
                            sp = sel.Path
                            if sp and (os.path.isfile(sp) or os.path.isdir(sp)):
                                resolved_paths.append(os.path.abspath(sp))
                        p = w.Document.Folder.Self.Path
                        if p and os.path.isdir(p) and p not in candidate_dirs:
                            candidate_dirs.append(p)
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"读取资源管理器窗口失败: {e}")

            # 2.2 加入当前工作区已存任务的目录
            try:
                state = self.get_workspace_state()
                for t in state.get("tasks", []):
                    fp = t.get("path")
                    if fp and os.path.exists(fp):
                        d = os.path.dirname(os.path.abspath(fp))
                        if d not in candidate_dirs:
                            candidate_dirs.append(d)
            except Exception:
                pass

            # 2.3 加入最近访问的目录 (Recent)
            try:
                recent_dir = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Recent")
                if os.path.isdir(recent_dir):
                    import win32com.client
                    wsh = win32com.client.Dispatch("WScript.Shell")
                    for lnk in sorted(Path(recent_dir).glob("*.lnk"), key=os.path.getmtime, reverse=True)[:20]:
                        try:
                            target = wsh.CreateShortcut(str(lnk)).TargetPath
                            if target and os.path.isdir(target) and target not in candidate_dirs:
                                candidate_dirs.append(target)
                            elif target and os.path.isfile(target):
                                td = os.path.dirname(target)
                                if td not in candidate_dirs:
                                    candidate_dirs.append(td)
                        except Exception:
                            pass
            except Exception:
                pass

            # 2.4 加入常用桌面和下载目录
            for special in [Path.home() / "Desktop", Path.home() / "Downloads"]:
                sp = str(special)
                if os.path.isdir(sp) and sp not in candidate_dirs:
                    candidate_dirs.append(sp)

            # 针对未匹配的 meta 进行比对
            for meta in unmatched_metas:
                target_name = meta.get("name")
                target_size = meta.get("size")
                if not target_name:
                    continue

                for cdir in candidate_dirs:
                    cand_path = os.path.join(cdir, target_name)
                    if os.path.isfile(cand_path):
                        if target_size is not None and target_size > 0:
                            if os.path.getsize(cand_path) == target_size:
                                resolved_paths.append(os.path.abspath(cand_path))
                                break
                        else:
                            resolved_paths.append(os.path.abspath(cand_path))
                            break
                    elif os.path.isdir(cand_path):
                        resolved_paths.append(os.path.abspath(cand_path))
                        break

        # 3. 解析为前端所需的完整任务数据
        if resolved_paths:
            return self.resolve_dropped_paths(resolved_paths)
        return []

    def _get_file_info(self, file_path: str) -> Optional[dict]:
        try:
            st = os.stat(file_path)
            abs_path = os.path.abspath(file_path)
            base_no_ext, ext = os.path.splitext(abs_path)
            ext = ext.lower()
            video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.ts', '.webm', '.m4v'}
            is_video = ext in video_exts

            # 自动检测同目录下是否已生成同名字幕文件
            completed = False
            save_path = None
            for sub_ext in ('.srt', '.txt', '.ass', '.vtt', '.lrc'):
                candidate = base_no_ext + sub_ext
                if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
                    completed = True
                    save_path = candidate
                    break

            return {
                "path": abs_path,
                "name": os.path.basename(abs_path),
                "dir": os.path.dirname(abs_path),
                "size": st.st_size,
                "isVideo": is_video,
                "ext": ext,
                "completed": completed,
                "savePath": save_path
            }
        except Exception as e:
            logger.debug(f"获取文件信息失败 {file_path}: {e}")
            return None

    def get_workspace_state(self) -> dict:
        """读取上次关闭前保存的工作区任务列表与设置"""
        state_file = Path(current_dir) / "workspace_state.json"
        if not state_file.is_file():
            return {}
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            tasks = data.get("tasks", [])
            valid_tasks = []
            for t in tasks:
                if not isinstance(t, dict) or not t.get("path"):
                    continue
                fp = t["path"]
                if not os.path.exists(fp):
                    continue
                base_no_ext = os.path.splitext(fp)[0]
                # 同步磁盘最新字幕状态
                found_sub = None
                for sub_ext in ('.srt', '.txt', '.ass', '.vtt', '.lrc'):
                    cand = base_no_ext + sub_ext
                    if os.path.exists(cand) and os.path.getsize(cand) > 0:
                        found_sub = cand
                        break
                if found_sub:
                    t["status"] = "completed"
                    t["progress"] = 100
                    t["stageMessage"] = "已完成"
                    t["savePath"] = found_sub
                    t["error"] = None
                elif t.get("status") == "processing":
                    t["status"] = "pending"
                    t["progress"] = 0
                    t["stageMessage"] = "等待继续..."
                valid_tasks.append(t)
            data["tasks"] = valid_tasks
            return data
        except Exception as e:
            logger.warning(f"读取工作区状态失败: {e}")
            return {}

    def save_workspace_state(self, state: dict) -> dict:
        """持久化保存工作区任务列表与设置"""
        state_file = Path(current_dir) / "workspace_state.json"
        try:
            with self._lock:
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
            return {"ok": True}
        except Exception as e:
            logger.warning(f"保存工作区状态失败: {e}")
            return {"ok": False}

    # ─────────────────────────────────────────────────────────────
    # 转录执行与控制
    # ─────────────────────────────────────────────────────────────
    def start_task(self, task_id: str, file_path: str, engine: str, export_format: str, keep_audio: bool = False) -> dict:
        """异步提交单项转录任务"""
        with self._lock:
            self._active_tasks[task_id] = True

        self._executor.submit(self._run_transcribe_worker, task_id, file_path, engine, export_format, keep_audio)
        return {"ok": True, "taskId": task_id}

    def cancel_task(self, task_id: str) -> dict:
        """取消任务"""
        with self._lock:
            if task_id in self._active_tasks:
                self._active_tasks[task_id] = False
        return {"ok": True}

    def _run_transcribe_worker(self, task_id: str, file_path: str, engine: str, export_format: str, keep_audio: bool):
        temp_audio = None
        is_converted = False
        try:
            save_ext = (export_format or 'srt').lower()
            base_no_ext = file_path.rsplit(".", 1)[0]
            save_path = f"{base_no_ext}.{save_ext}"

            self.emit_event("task_progress", {
                "taskId": task_id,
                "status": "processing",
                "stage": "inspecting",
                "message": "检查同名字幕...",
                "progress": 10
            })

            # 1. 极速复用：如果目标文件已存在且非空，直接复用完成，绝不重复转录或覆盖
            if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                with open(save_path, "r", encoding="utf-8", errors="ignore") as f:
                    result_text = f.read(500)
                self.emit_event("task_finished", {
                    "taskId": task_id,
                    "savePath": save_path,
                    "resultText": result_text[:400]
                })
                return

            # 2. 智能极速优化：如果同目录下已存在同名 .srt 或 .ass 字幕，直接转换生成目标格式，0秒完成！
            srt_path = f"{base_no_ext}.srt"
            ass_path = f"{base_no_ext}.ass"
            if save_ext == 'txt' and os.path.exists(srt_path):
                data = from_subtitle_file(srt_path)
                result_text = data.to_txt()
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(result_text)
                self.emit_event("task_finished", {
                    "taskId": task_id,
                    "savePath": save_path,
                    "resultText": result_text[:400]
                })
                return
            elif save_ext == 'ass' and os.path.exists(srt_path):
                data = from_subtitle_file(srt_path)
                result_text = data.to_ass()
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(result_text)
                self.emit_event("task_finished", {
                    "taskId": task_id,
                    "savePath": save_path,
                    "resultText": result_text[:400]
                })
                return

            # 音频准备（若已有上次提取好的同名 mp3 音频，直接复用免去重新转码并确保断点哈希一致）
            audio_exts = {'.mp3', '.wav'}
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in audio_exts:
                temp_audio = f"{base_no_ext}.mp3"
                if os.path.exists(temp_audio) and os.path.getsize(temp_audio) > 10240:
                    self.emit_event("task_progress", {
                        "taskId": task_id,
                        "status": "processing",
                        "stage": "extracting",
                        "message": "已复用本地音频，直接进入断点续传...",
                        "progress": 35
                    })
                else:
                    self.emit_event("task_progress", {
                        "taskId": task_id,
                        "status": "processing",
                        "stage": "extracting",
                        "message": "提取音频中 (ffmpeg)...",
                        "progress": 25
                    })
                    if not video2audio(file_path, temp_audio):
                        raise Exception("音频提取失败，请检查 ffmpeg 是否正常")
                target_audio = temp_audio
                is_converted = True
            else:
                target_audio = file_path

            # 检查任务是否被中止
            if not self._active_tasks.get(task_id, True):
                return

            self.emit_event("task_progress", {
                "taskId": task_id,
                "status": "processing",
                "stage": "transcribing",
                "message": f"转录中 ({engine})...",
                "progress": 40
            })

            # 实例化 ASR 引擎
            use_cache = True
            if engine in ['B 接口', 'bcut', 'B站接口']:
                asr = BcutASR(target_audio, use_cache=use_cache)
            elif engine in ['J 接口', 'jianying', '剪映接口']:
                asr = JianYingASR(target_audio, use_cache=use_cache)
            elif engine in ['Whisper', 'whisper']:
                asr = WhisperASR(target_audio, use_cache=use_cache)
            else:
                asr = BcutASR(target_audio, use_cache=use_cache)

            last_ui_pct = [40]

            def _on_asr_progress(pct, msg):
                if pct is not None:
                    # 将 0~100 映射到 UI 的 40~88 区间
                    mapped = int(40 + (max(0, min(100, pct)) / 100.0) * 48)
                    last_ui_pct[0] = mapped
                self.emit_event("task_progress", {
                    "taskId": task_id,
                    "status": "processing",
                    "stage": "transcribing",
                    "message": msg or f"转录中 ({engine})...",
                    "progress": last_ui_pct[0]
                })

            result = asr.run(callback=_on_asr_progress)

            self.emit_event("task_progress", {
                "taskId": task_id,
                "status": "processing",
                "stage": "formatting",
                "message": "导出字幕格式...",
                "progress": 90
            })

            # 导出字幕
            if save_ext == 'srt':
                result_text = result.to_srt()
            elif save_ext == 'ass':
                result_text = result.to_ass()
            elif save_ext == 'txt':
                result_text = result.to_txt()
            elif save_ext == 'vtt':
                result_text = result.to_vtt() if hasattr(result, 'to_vtt') else result.to_srt()
            elif save_ext == 'lrc':
                result_text = result.to_lrc() if hasattr(result, 'to_lrc') else result.to_srt()
            elif save_ext == 'json':
                result_text = result.to_json() if hasattr(result, 'to_json') else json.dumps(result.to_dict(), ensure_ascii=False)
            else:
                result_text = result.to_srt()

            with open(save_path, "w", encoding="utf-8") as f:
                f.write(result_text)

            # 仅在任务彻底完成后才清理临时转换的音频（若未勾选保留音频）
            if is_converted and not keep_audio and temp_audio and os.path.exists(temp_audio):
                try:
                    os.remove(temp_audio)
                except Exception:
                    pass

            self.emit_event("task_finished", {
                "taskId": task_id,
                "savePath": save_path,
                "resultText": result_text[:400]
            })

        except Exception as e:
            # 若中途因配额或网络中断，保留有效的已提取 mp3（>10KB），以便下次重试免转码秒级续传
            if is_converted and temp_audio and os.path.exists(temp_audio):
                try:
                    if os.path.getsize(temp_audio) <= 10240:
                        os.remove(temp_audio)
                except Exception:
                    pass
            logger.error(f"任务 {task_id} 出错: {e}")
            self.emit_event("task_error", {
                "taskId": task_id,
                "error": str(e)
            })

    # ─────────────────────────────────────────────────────────────
    # 辅助工具：打开目录、预览、快速导出
    # ─────────────────────────────────────────────────────────────
    def open_in_folder(self, file_path: str) -> bool:
        """在 Windows 资源管理器中打开并高亮选中文件"""
        if not file_path or not os.path.exists(file_path):
            return False
        norm = os.path.normpath(file_path)
        try:
            if platform.system() == 'Windows':
                subprocess.run(['explorer', '/select,', norm], check=False)
            elif platform.system() == 'Darwin':
                subprocess.run(['open', '-R', norm], check=False)
            else:
                subprocess.run(['xdg-open', os.path.dirname(norm)], check=False)
            return True
        except Exception as e:
            logger.error(f"打开文件目录失败: {e}")
            return False

    def read_subtitle_content(self, file_path: str, format_type: str = "srt") -> dict:
        """读取转录结果文本用于弹窗预览"""
        base_no_ext = file_path.rsplit(".", 1)[0]
        ext = format_type.lower()
        target_path = f"{base_no_ext}.{ext}"

        if not os.path.exists(target_path):
            # 尝试回退查找同名 srt 或 txt
            if os.path.exists(f"{base_no_ext}.srt"):
                target_path = f"{base_no_ext}.srt"
            elif os.path.exists(f"{base_no_ext}.txt"):
                target_path = f"{base_no_ext}.txt"
            else:
                return {"ok": False, "error": "未找到已生成的字幕或文本文件"}

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {
                "ok": True,
                "path": target_path,
                "content": content
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def fast_export_txt(self, file_path: str) -> dict:
        """从同名字幕极速转换为 txt"""
        base_no_ext = file_path.rsplit(".", 1)[0]
        srt_path = f"{base_no_ext}.srt"
        ass_path = f"{base_no_ext}.ass"
        txt_path = f"{base_no_ext}.txt"

        try:
            if os.path.exists(srt_path):
                data = from_subtitle_file(srt_path)
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(data.to_txt())
                return {"ok": True, "path": txt_path}
            elif os.path.exists(ass_path):
                data = from_subtitle_file(ass_path)
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(data.to_txt())
                return {"ok": True, "path": txt_path}
            else:
                return {"ok": False, "error": "同目录下不存在 SRT 或 ASS 字幕文件"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ─────────────────────────────────────────────────────────────
    # 配置管理 (Whisper & 代理池)
    # ─────────────────────────────────────────────────────────────
    def get_config(self) -> dict:
        """获取当前配置信息"""
        config_path = Path(current_dir) / "whisper_config.json"
        cfg = {}
        if config_path.is_file():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                pass

        # 代理池
        bcut_proxies = bcut_proxy_pool.get_all_raw_proxies()
        whisper_proxies = whisper_proxy_pool.get_all_raw_proxies()

        return {
            "whisper": {
                "base_url": cfg.get("base_url", "https://api.openai.com/v1"),
                "api_key": cfg.get("api_key", ""),
                "model": cfg.get("model", "whisper-1"),
                "prompt": cfg.get("prompt", ""),
                "temperature": cfg.get("temperature", 0.0),
                "threads": cfg.get("threads", 3),
                "proxies": whisper_proxies
            },
            "bcut_proxies": bcut_proxies,
            "whisper_proxies": whisper_proxies,
            "system": {
                "ffmpeg": os.path.isfile(get_ffmpeg_path()),
                "platform": platform.platform(),
                "python": sys.version.split()[0]
            }
        }

    def save_config(self, new_config: dict) -> dict:
        """保存配置"""
        config_path = Path(current_dir) / "whisper_config.json"
        try:
            cfg = {}
            if config_path.is_file():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass

            whisper_part = new_config.get("whisper", {})
            cfg["base_url"] = whisper_part.get("base_url", "https://api.openai.com/v1")
            cfg["api_key"] = whisper_part.get("api_key", "")
            cfg["model"] = whisper_part.get("model", "whisper-1")
            cfg["prompt"] = whisper_part.get("prompt", "")
            cfg["temperature"] = float(whisper_part.get("temperature", 0.0))
            cfg["threads"] = int(whisper_part.get("threads", 3))

            # Whisper 代理列表保存
            whisper_px_input = new_config.get("whisper_proxies")
            if whisper_px_input is None:
                whisper_px_input = whisper_part.get("proxies", [])
            clean_whisper_proxies = []
            for p in whisper_px_input:
                p_str = str(p).strip()
                if p_str and not p_str.startswith("#"):
                    clean_whisper_proxies.append(p_str)
            cfg["whisper_proxies"] = clean_whisper_proxies
            # 兼容保留单一 proxy 字段（使用首个节点）
            if clean_whisper_proxies:
                cfg["proxy"] = clean_whisper_proxies[0]
            elif "proxy" in cfg:
                del cfg["proxy"]

            whisper_proxy_pool.set_proxies(clean_whisper_proxies)

            # Bcut 代理列表保存
            proxies_input = new_config.get("bcut_proxies", [])
            clean_proxies = []
            for p in proxies_input:
                p_str = str(p).strip()
                if p_str and not p_str.startswith("#"):
                    clean_proxies.append(p_str)

            cfg["bcut_proxies"] = clean_proxies
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)

            # 同步更新 bcut_proxies.txt
            bcut_txt = Path(current_dir) / "bcut_proxies.txt"
            with open(bcut_txt, "w", encoding="utf-8") as f:
                f.write("# 音流 (VoiceFlow Studio) B 接口代理池配置 (每行一个)\n")
                for p in clean_proxies:
                    f.write(f"{p}\n")

            # 刷新内存代理池
            bcut_proxy_pool.set_proxies(clean_proxies)

            return {"ok": True, "bcutCount": len(clean_proxies), "whisperCount": len(clean_whisper_proxies)}
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return {"ok": False, "error": str(e)}

    def test_single_proxy(self, proxy_str: str, target_type: str = "bcut") -> dict:
        """测试单个代理节点的连通性与延迟"""
        ok, msg = BcutProxyPool.test_single_proxy(proxy_str, timeout=6, target_type=target_type)
        return {"ok": ok, "message": msg}

    def check_app_update(self) -> dict:
        """检查软件更新"""
        try:
            from check_update import check_update, check_internet_connection
            if not check_internet_connection():
                return {"hasUpdate": False, "message": "无法连接到互联网"}
            cfg = check_update(None)
            if cfg and cfg.get("update_download_url"):
                return {
                    "hasUpdate": True,
                    "url": cfg.get("update_download_url"),
                    "force": cfg.get("fource", False),
                    "version": cfg.get("version", "")
                }
            return {"hasUpdate": False, "message": "已是最新版本"}
        except Exception as e:
            return {"hasUpdate": False, "message": str(e)}

    def open_external_url(self, url: str):
        """用系统默认浏览器打开链接"""
        if url:
            webbrowser.open(url)


def main():
    api = DesktopApi()
    
    # 优先加载本地编译的前端静态资源
    candidates = [
        os.path.join(current_dir, "frontend", "dist"),
        os.path.join(current_dir, "dist"),
        os.path.join(os.path.dirname(current_dir), "frontend", "dist"),
        os.path.join(os.path.dirname(current_dir), "dist"),
    ]
    frontend_dist_dir = next((p for p in candidates if os.path.isdir(p) and os.path.isfile(os.path.join(p, "index.html"))), None)
    dev_url = "http://127.0.0.1:5173"

    # 判断是否处于开发模式（如果指定了 --dev 参数或找不到静态包）
    use_dev = "--dev" in sys.argv
    if use_dev or not frontend_dist_dir:
        target_url = dev_url
    else:
        # 启动内置本地极速 HTTP 服务，解决 Windows 下 file:// 协议对 ES Module (Vite) 的 CORS 白屏拦截
        import http.server
        import socketserver
        import threading

        class DistHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=frontend_dist_dir, **kwargs)
            def log_message(self, format, *args):
                pass

        httpd = socketserver.TCPServer(('127.0.0.1', 0), DistHandler)
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        target_url = f"http://127.0.0.1:{port}/index.html"
        logger.info(f"本地静态服务已就绪: {target_url}")


    window = webview.create_window(
        title="音流（VoiceFlow Studio）—— 多引擎并发 AI 语音识别与智能字幕工作台",
        url=target_url,
        js_api=api,
        width=1120,
        height=760,
        min_size=(880, 600),
        background_color="#0e0e14"
    )
    api.set_window(window)

    def on_window_shown():
        try:
            from webview.platforms.winforms import BrowserView
            try:
                from webview.platforms.winforms import DwmSetWindowAttribute
            except (ImportError, AttributeError):
                import ctypes
                def DwmSetWindowAttribute(hwnd, attr, val):
                    try:
                        c_val = ctypes.c_int(val)
                        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(c_val), ctypes.sizeof(c_val))
                    except Exception:
                        pass
            form = BrowserView.instances.get(window.uid)
            if form:
                def _apply_theme_and_dnd():
                    try:
                        hwnd = form.Handle.ToInt32()
                        # 1. 强制沉浸式深色模式
                        DwmSetWindowAttribute(hwnd, 20, 1)
                        # 2. 纯黑标题栏底色 (0x00000000)
                        DwmSetWindowAttribute(hwnd, 35, 0)
                        # 3. 标题文字高对比暗白 (#e8e8ed -> 0x00EDE8E8)
                        DwmSetWindowAttribute(hwnd, 36, 0x00EDE8E8)
                        # 4. 纯黑外边框
                        DwmSetWindowAttribute(hwnd, 34, 0)
                    except Exception as err:
                        logger.error(f"初始化窗体沉浸式主题失败: {err}")

                if form.InvokeRequired:
                    try:
                        from System import Action
                        form.BeginInvoke(Action(_apply_theme_and_dnd))
                    except Exception:
                        _apply_theme_and_dnd()
                else:
                    _apply_theme_and_dnd()
        except Exception as e:
            logger.error(f"on_window_shown 异常: {e}")

    def on_window_loaded():
        try:
            from webview.dom import DOMEventHandler, _dnd_state

            def on_drop(e):
                try:
                    logger.info("捕获到 pywebview 原生 DOM drop 事件")
                    files = e.get('dataTransfer', {}).get('files', [])
                    paths = [f.get('pywebviewFullPath') for f in files if f.get('pywebviewFullPath')]

                    # 如果有未被 JS 名称严格匹配消耗的原生 CoreWebView2File 路径，从 _dnd_state['paths'] 补齐
                    if _dnd_state.get('paths'):
                        for item in list(_dnd_state['paths']):
                            if isinstance(item, (list, tuple)) and len(item) > 1:
                                paths.append(item[1])
                            elif isinstance(item, str):
                                paths.append(item)
                        _dnd_state['paths'].clear()

                    # 路径去重并保序
                    unique_paths = []
                    seen = set()
                    for p in paths:
                        if p and p not in seen:
                            seen.add(p)
                            unique_paths.append(p)

                    logger.info(f"提取到拖拽文件/文件夹路径: {unique_paths}")
                    if unique_paths:
                        resolved = api.resolve_dropped_paths(unique_paths)
                        if resolved:
                            payload_json = json.dumps(resolved, ensure_ascii=False)
                            js_code = f"if (window.__onDesktopEvent) {{ window.__onDesktopEvent('dropped_files', {payload_json}); }}"
                            window.evaluate_js(js_code)
                            logger.info(f"已成功向前端投递 {len(resolved)} 个文件任务")
                        else:
                            toast_payload = json.dumps({"message": "未检测到支持的音视频格式文件", "type": "warning"}, ensure_ascii=False)
                            js_code = f"if (window.__onDesktopEvent) {{ window.__onDesktopEvent('toast', {toast_payload}); }}"
                            window.evaluate_js(js_code)
                except Exception as err:
                    logger.error(f"处理 DOM drop 事件异常: {err}", exc_info=True)

            if hasattr(window, 'dom') and hasattr(window.dom, 'document'):
                window.dom.document.on('drop', DOMEventHandler(on_drop, prevent_default=True, stop_propagation=False))
                logger.info("已成功激活 pywebview DOM 原生文件与文件夹拖拽接收管道")
        except (ImportError, ModuleNotFoundError, AttributeError):
            logger.debug("当前环境不支持 DOM drop 监听，已保持兼容运行")
        except Exception as e:
            logger.error(f"注册 DOM drop 监听器异常: {e}", exc_info=True)

    # 兼容 pywebview 5.x (window.events) 与 pywebview 3.x/4.x (window.shown / window.loaded)
    if hasattr(window, 'events'):
        window.events.shown += on_window_shown
        if hasattr(window.events, 'loaded'):
            window.events.loaded += on_window_loaded
    else:
        if hasattr(window, 'shown'):
            window.shown += on_window_shown
        if hasattr(window, 'loaded'):
            window.loaded += on_window_loaded

    logger.info("启动「音流 (VoiceFlow Studio)」WebView 桌面工作台...")
    ico_path = os.path.join(current_dir, "app_icon.ico")
    try:
        webview.start(http_server=True, debug=use_dev, icon=ico_path if os.path.isfile(ico_path) else None)
    except TypeError:
        webview.start(http_server=True, debug=use_dev)




def start():
    main()


if __name__ == '__main__':
    start()


