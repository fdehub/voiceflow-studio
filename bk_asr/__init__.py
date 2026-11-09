from .BcutASR import BcutASR
from .JianYingASR import JianYingASR
from .WhisperASR import WhisperASR
from .ProxyPool import bcut_proxy_pool

__all__ = ["BcutASR", "JianYingASR", "WhisperASR", "bcut_proxy_pool"]


def transcribe(audio_file, platform):
    assert platform in __all__
    asr = globals()[platform](audio_file)
    return asr.run()
