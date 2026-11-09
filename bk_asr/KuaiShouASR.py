import requests

from .ASRData import ASRDataSeg
from .BaseASR import BaseASR


class KuaiShouASR(BaseASR):
    def __init__(self, audio_path: [str, bytes], use_cache: bool = False):
        super().__init__(audio_path, use_cache)

    def _run(self, callback=None) -> dict:
        if callback:
            callback(50, "正在通过快手接口识别中...")
        res = self._submit()
        if not isinstance(res, dict) or not res.get('data') or not res['data'].get('text'):
            msg = res.get('msg', '接口未返回有效数据') if isinstance(res, dict) else str(res)
            raise RuntimeError(f"快手 ASR 接口调用失败（官方已禁用该公开接口）: {msg}")
        if callback:
            callback(100, "转录完成")
        return res

    def _make_segments(self, resp_data: dict) -> list[ASRDataSeg]:
        return [ASRDataSeg(u['text'], u['start_time'], u['end_time']) for u in resp_data['data']['text']]

    def _submit(self) -> dict:
        payload = {
            "typeId": "1"
        }
        files = [('file', ('test.mp3', self.file_binary, 'audio/mpeg'))]
        result = requests.post("https://ai.kuaishou.com/api/effects/subtitle_generate", data=payload, files=files)
        return result.json()
