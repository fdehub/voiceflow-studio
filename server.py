import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp

from bk_asr.BcutASR import BcutASR
from bk_asr.JianYingASR import JianYingASR
from bk_asr.WhisperASR import WhisperASR
from fastapi import BackgroundTasks
import threading
import time

jobs = {}
jobs_lock = threading.Lock()

def update_job_progress(job_id: str, progress: int, message: str, result=None, error=None):
    with jobs_lock:
        if job_id not in jobs:
            jobs[job_id] = {}
        jobs[job_id]["progress"] = progress
        jobs[job_id]["message"] = message
        if result is not None:
            jobs[job_id]["result"] = result
        if error is not None:
            jobs[job_id]["error"] = error


app = FastAPI(
    title="音流 (VoiceFlow Studio) Web API",
    description="多引擎并发 AI 语音识别与智能字幕工作台"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def video2audio(input_file: str, output: str = "") -> bool:
    """Extract audio from video using ffmpeg"""
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        'ffmpeg',
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
    try:
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
    except Exception as e:
        print(f"FFmpeg error: {e}")
        return False


def process_audio(file_path: str, engine: str, job_id: str = None) -> dict:
    audio_path = file_path
    audio_exts = ['.mp3', '.wav']
    
    def callback(progress, msg):
        if job_id:
            update_job_progress(job_id, progress, msg)
            
    if job_id:
        update_job_progress(job_id, 10, "正在提取音频...")
    
    if not any(file_path.lower().endswith(ext) for ext in audio_exts):
        temp_audio = str(Path(file_path).with_suffix(".mp3"))
        if not video2audio(file_path, temp_audio):
            raise Exception("Failed to convert video to audio. Is ffmpeg installed?")
        audio_path = temp_audio

    try:
        if engine == 'B 接口':
            asr = BcutASR(audio_path, use_cache=True)
        elif engine == 'J 接口':
            asr = JianYingASR(audio_path, use_cache=True)
        elif engine in ['Whisper', 'Whisper 接口']:
            asr = WhisperASR(audio_path, use_cache=True)
        else:
            raise ValueError(f"Unknown engine: {engine}")

        result = asr.run(callback=callback)
        res = {
            "txt": result.to_txt(),
            "srt": result.to_srt(),
            "ass": result.to_ass()
        }
        if job_id:
            update_job_progress(job_id, 100, "转换完成！", result=res)
        return res
    except Exception as e:
        if job_id:
            update_job_progress(job_id, 0, "转换失败", error=f"ASR Error: {str(e)}")
        raise e


@app.post("/api/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    engine: str = Form("J 接口")
):
    ext = Path(file.filename).suffix
    unique_id = str(uuid.uuid4())
    temp_file = UPLOAD_DIR / f"{unique_id}{ext}"
    
    with open(temp_file, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    job_id = str(uuid.uuid4())
    update_job_progress(job_id, 0, "等待开始...")
    
    def background_upload_task():
        try:
            update_job_progress(job_id, 5, "文件已上传，准备转换...")
            process_audio(str(temp_file), engine, job_id=job_id)
        except Exception as e:
            update_job_progress(job_id, 0, "处理失败", error=str(e))
        finally:
            if temp_file.exists():
                temp_file.unlink()
            temp_audio = temp_file.with_suffix(".mp3")
            if temp_audio.exists():
                temp_audio.unlink()
                
    background_tasks.add_task(background_upload_task)
    return {"success": True, "job_id": job_id}


class UrlRequest(BaseModel):
    url: str
    engine: str = "J 接口"

def background_url_task(req: UrlRequest, job_id: str, unique_id: str):
    import re
    try:
        # Extract the actual URL from the text (e.g. from a Douyin share text)
        url_match = re.search(r'(https?://[^\s]+)', req.url)
        if not url_match:
            raise Exception("未找到有效的网络链接，请重新复制。")
        actual_url = url_match.group(1)

        downloaded_file = None
        if "douyin.com" in actual_url:
            update_job_progress(job_id, 5, "正在解析抖音链接...")
            script_path = r"C:\Users\bigtree\Desktop\dyt\get_dy_video.py"
            cmd = ['python', script_path, actual_url]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=r"C:\Users\bigtree\Desktop\dyt")
            if result.returncode != 0 or "ERROR" in result.stdout:
                raise Exception(f"Douyin API Error: {result.stdout.strip() or result.stderr.strip()}")
            
            video_url = result.stdout.strip()
            if not video_url or not video_url.startswith("http"):
                raise Exception("Failed to extract video URL")
                
            update_job_progress(job_id, 15, "正在下载视频...")
            downloaded_file = UPLOAD_DIR / f"{unique_id}.mp4"
            import requests
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Referer": "https://www.douyin.com/"
            }
            dl_res = requests.get(video_url, headers=headers, stream=True)
            if dl_res.status_code != 200:
                raise Exception(f"Download failed: HTTP Error {dl_res.status_code}")
                
            total_size = int(dl_res.headers.get('content-length', 0))
            downloaded_size = 0
            with open(downloaded_file, 'wb') as f:
                for chunk in dl_res.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            prog = 15 + int((downloaded_size / total_size) * 15)
                            update_job_progress(job_id, min(30, prog), f"正在下载视频... {downloaded_size//1024//1024}MB / {total_size//1024//1024}MB")
        else:
            update_job_progress(job_id, 5, "正在准备下载...")
            output_template = str(UPLOAD_DIR / f"{unique_id}.%(ext)s")
            
            def my_hook(d):
                if d['status'] == 'downloading':
                    p = d.get('_percent_str', '0%').replace('%', '').strip()
                    try:
                        p_val = float(p)
                        prog = 5 + int(p_val * 0.25) # Up to 30%
                        update_job_progress(job_id, min(30, prog), f"正在下载... {d.get('_percent_str', '0%')}")
                    except ValueError:
                        pass

            ydl_opts = {
                'format': 'best',
                'outtmpl': output_template,
                'quiet': True,
                'progress_hooks': [my_hook]
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(actual_url, download=True)
                ext = info.get('ext', 'mp4')
                downloaded_file = UPLOAD_DIR / f"{unique_id}.{ext}"
                
        if not downloaded_file or not downloaded_file.exists():
            raise Exception("Failed to download video")
            
        process_audio(str(downloaded_file), req.engine, job_id=job_id)
    except Exception as e:
        update_job_progress(job_id, 0, "处理失败", error=str(e))
    finally:
        for ext in ['mp4', 'mkv', 'webm', 'mp3', 'wav']:
            f = UPLOAD_DIR / f"{unique_id}.{ext}"
            if f.exists():
                try:
                    f.unlink()
                except:
                    pass

@app.post("/api/url")
async def process_url(req: UrlRequest, background_tasks: BackgroundTasks):
    unique_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    update_job_progress(job_id, 0, "任务已排队...")
    background_tasks.add_task(background_url_task, req, job_id, unique_id)
    return {"success": True, "job_id": job_id}

@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        return jobs[job_id]

@app.post("/api/sync_url")
async def process_sync_url(req: UrlRequest):
    import re
    try:
        url_match = re.search(r'(https?://[^\s]+)', req.url)
        if not url_match:
            raise HTTPException(status_code=400, detail="未找到有效的网络链接")
        actual_url = url_match.group(1)

        downloaded_file = None
        if "douyin.com" in actual_url:
            script_path = r"C:\Users\bigtree\Desktop\dyt\get_dy_video.py"
            cmd = ['python', script_path, actual_url]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=r"C:\Users\bigtree\Desktop\dyt")
            if result.returncode != 0 or "ERROR" in result.stdout:
                raise Exception(f"Douyin API Error: {result.stdout.strip() or result.stderr.strip()}")
            
            video_url = result.stdout.strip()
            if not video_url or not video_url.startswith("http"):
                raise Exception("Failed to extract video URL")
                
            downloaded_file = UPLOAD_DIR / f"{uuid.uuid4()}.mp4"
            import requests
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Referer": "https://www.douyin.com/"
            }
            dl_res = requests.get(video_url, headers=headers, stream=True)
            if dl_res.status_code != 200:
                raise Exception(f"Download failed: HTTP Error {dl_res.status_code}")
                
            with open(downloaded_file, 'wb') as f:
                for chunk in dl_res.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        else:
            output_template = str(UPLOAD_DIR / f"{uuid.uuid4()}.%(ext)s")
            ydl_opts = {
                'format': 'best',
                'outtmpl': output_template,
                'quiet': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(actual_url, download=True)
                ext = info.get('ext', 'mp4')
                downloaded_file = UPLOAD_DIR / f"{uuid.uuid4()}.{ext}"
                
        if not downloaded_file or not downloaded_file.exists():
            raise Exception("Failed to download video")
            
        res = process_audio(str(downloaded_file), req.engine)
        return {"success": True, "text": res["txt"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if downloaded_file and downloaded_file.exists():
            try:
                downloaded_file.unlink()
            except:
                pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5637)
