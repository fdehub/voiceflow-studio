import json
import logging
import time
from os import PathLike
from typing import Optional, Union

import requests

from .ASRData import ASRData, ASRDataSeg
from .BaseASR import BaseASR
from .ProxyPool import bcut_proxy_pool, normalize_proxy, to_requests_proxies


__version__ = "0.0.3"

API_BASE_URL = "https://member.bilibili.com/x/bcut/rubick-interface"

# 申请上传
API_REQ_UPLOAD = API_BASE_URL + "/resource/create"

# 提交上传
API_COMMIT_UPLOAD = API_BASE_URL + "/resource/create/complete"

# 创建任务
API_CREATE_TASK = API_BASE_URL + "/task"

# 查询结果
API_QUERY_RESULT = API_BASE_URL + "/task/result"


class BcutASR(BaseASR):
    """必剪 语音识别接口"""
    headers = {
        'User-Agent': 'Bilibili/1.0.0 (https://www.bilibili.com)',
        'Content-Type': 'application/json'
    }

    def __init__(self, audio_path: [str, bytes], use_cache: bool = False, proxy: Optional[str] = None):
        super().__init__(audio_path, use_cache=use_cache)
        self.session = requests.Session()
        self.current_proxy_raw = None

        if proxy:
            self.current_proxy_raw = proxy
            self.session.proxies = to_requests_proxies(normalize_proxy(proxy))
        else:
            self.rotate_proxy()

        self.task_id = None
        self.__etags = []
        self.__in_boss_key: Optional[str, None] = None
        self.__resource_id: Optional[str, None] = None
        self.__upload_id: Optional[str, None] = None
        self.__upload_urls: Optional[list[str]] = []
        self.__per_size: Optional[int, None] = None
        self.__clips: Optional[int, None] = None
        self.__download_url: Optional[str, None] = None

    def rotate_proxy(self):
        """从专属代理池获取下一个可用代理节点"""
        node_tuple = bcut_proxy_pool.get_proxy()
        if node_tuple:
            self.current_proxy_raw, proxies_dict = node_tuple
            self.session.proxies = proxies_dict
            logging.info(f"[BcutASR] 切换/使用代理节点: {self.current_proxy_raw}")
        else:
            self.current_proxy_raw = None
            self.session.proxies = {}
            logging.info("[BcutASR] 代理池未配置或无可用代理，使用本地直连/系统代理")

    def upload(self) -> None:
        """申请上传"""
        if not self.file_binary:
            raise ValueError("none set data")
        payload = json.dumps({
            "type": 2,
            "name": "audio.mp3",
            "size": len(self.file_binary),
            "ResourceFileType": "mp3",
            "model_id": "8",
        })

        resp = self.session.post(
            API_REQ_UPLOAD,
            data=payload,
            headers=self.headers,
            timeout=30
        )
        resp.raise_for_status()
        resp = resp.json()
        if resp.get("code", 0) != 0:
            raise RuntimeError(f"Bcut 申请上传被拒绝: code={resp.get('code')}, {resp.get('message', '')}")
        resp_data = resp["data"]

        self.__in_boss_key = resp_data["in_boss_key"]
        self.__resource_id = resp_data["resource_id"]
        self.__upload_id = resp_data["upload_id"]
        self.__upload_urls = resp_data["upload_urls"]
        self.__per_size = resp_data["per_size"]
        self.__clips = len(resp_data["upload_urls"])

        logging.info(
            f"申请上传成功, 总计大小{resp_data['size'] // 1024}KB, {self.__clips}分片, 分片大小{resp_data['per_size'] // 1024}KB: {self.__in_boss_key}"
        )
        self.__upload_part()
        self.__commit_upload()

    def __upload_part(self) -> None:
        """上传音频数据"""
        self.__etags = []
        for clip in range(self.__clips):
            start_range = clip * self.__per_size
            end_range = (clip + 1) * self.__per_size
            logging.info(f"开始上传分片{clip}: {start_range}-{end_range}")
            resp = self.session.put(
                self.__upload_urls[clip],
                data=self.file_binary[start_range:end_range],
                headers=self.headers,
                timeout=60
            )
            resp.raise_for_status()
            etag = resp.headers.get("Etag")
            self.__etags.append(etag)
            logging.info(f"分片{clip}上传成功: {etag}")

    def __commit_upload(self) -> None:
        """提交上传数据"""
        data = json.dumps({
            "InBossKey": self.__in_boss_key,
            "ResourceId": self.__resource_id,
            "Etags": ",".join(self.__etags),
            "UploadId": self.__upload_id,
            "model_id": "8",
        })
        resp = self.session.post(
            API_COMMIT_UPLOAD,
            data=data,
            headers=self.headers,
            timeout=30
        )
        resp.raise_for_status()
        resp = resp.json()
        self.__download_url = resp["data"]["download_url"]
        logging.info(f"提交成功")

    def create_task(self) -> str:
        """开始创建转换任务"""
        resp = self.session.post(
            API_CREATE_TASK, json={"resource": self.__download_url, "model_id": "8"}, headers=self.headers, timeout=30
        )
        resp.raise_for_status()
        resp = resp.json()
        self.task_id = resp["data"]["task_id"]
        logging.info(f"任务已创建: {self.task_id}")
        return self.task_id

    def result(self, task_id: Optional[str] = None):
        """查询转换结果"""
        resp = self.session.get(API_QUERY_RESULT, params={"model_id": 7, "task_id": task_id or self.task_id}, headers=self.headers, timeout=30)
        resp.raise_for_status()
        resp = resp.json()
        return resp["data"]

    def _run(self, callback=None) -> dict:
        max_attempts = max(3, len(bcut_proxy_pool.get_all_raw_proxies()) + 1)
        last_err = None

        for attempt in range(max_attempts):
            try:
                if callback:
                    callback(20, "申请上传...")
                self.upload()
                if callback:
                    callback(40, "提交任务...")
                self.create_task()
                if callback:
                    callback(60, "查询转录结果...")
                while True:
                    resp_data = self.result()
                    if resp_data['state'] == 4:
                        if callback:
                            callback(100, "转录完成")
                        logging.info(f"转换成功")
                        bcut_proxy_pool.report_result(self.current_proxy_raw, True)
                        return json.loads(resp_data["result"])
                    elif resp_data['state'] == 3:
                        raise Exception("BcutASR failed to recognize")

                    if callback:
                        callback(60 + min(35, resp_data.get('progress', 0) // 2), "正在识别音频中...")

                    time.sleep(2)
            except Exception as e:
                last_err = e
                logging.warning(f"[BcutASR] 执行异常 (当前代理: {self.current_proxy_raw}): {e}")
                bcut_proxy_pool.report_result(self.current_proxy_raw, False)
                if attempt < max_attempts - 1 and bcut_proxy_pool.get_all_raw_proxies():
                    logging.info(f"[BcutASR] 自动切换下一个代理重试 (第 {attempt + 2}/{max_attempts} 次)...")
                    if callback:
                        callback(15, f"切换代理重试中...")
                    self.rotate_proxy()
                    time.sleep(1)
                    continue
                else:
                    raise e

    def _make_segments(self, resp_data: dict) -> list[ASRDataSeg]:
        return [ASRDataSeg(u['transcript'], u['start_time'], u['end_time']) for u in resp_data['utterances']]


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    # Example usage
    audio_file = r"test.mp3"
    asr = BcutASR(audio_file)
    asr_data = asr.run()
    print(asr_data)
