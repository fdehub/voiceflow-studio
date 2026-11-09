import json
import logging
import os
from pathlib import Path
import random
import re
import threading
import time
from typing import Dict, List, Optional, Tuple
import requests

# 确保 logging 已配置
logger = logging.getLogger("BcutProxyPool")


def normalize_proxy(proxy_str: str) -> Optional[str]:
    """格式化代理字符串，支持 http, https, socks5, socks5h，自动剔除尾部注释备注"""
    if not proxy_str or not isinstance(proxy_str, str):
        return None
    p = proxy_str.strip()
    if not p or p.startswith("#"):
        return None

    # 剥离尾部备注标签（如 #AS31898 美国 加利福尼亚 圣何塞）
    if "#" in p:
        p = p.split("#")[0].strip()
    if not p:
        return None

    # 如果用户没有写协议前缀（例如 127.0.0.1:10808），默认补齐 http://
    if not re.match(r'^(http|https|socks5|socks5h)://', p, re.IGNORECASE):
        p = f"http://{p}"

    # 如果是 socks5://，推荐转换为 socks5h:// 以便由远端代理进行域名 DNS 解析，彻底避免本地 DNS 污染
    if p.lower().startswith("socks5://"):
        p = "socks5h://" + p[len("socks5://"):]

    return p


def to_requests_proxies(proxy_url: Optional[str]) -> Optional[Dict[str, str]]:
    """转换为 requests 库所用的 proxies 字典"""
    if not proxy_url:
        return None
    return {
        "http": proxy_url,
        "https": proxy_url
    }


class ProxyNode:
    """代理节点状态记录"""

    def __init__(self, raw_url: str):
        self.raw_url = raw_url.strip()
        self.normalized_url = normalize_proxy(self.raw_url)
        self.fail_count = 0
        self.success_count = 0
        self.cooldown_until = 0.0  # 冷却截止时间戳
        self.last_used = 0.0

    @property
    def is_available(self) -> bool:
        return time.time() >= self.cooldown_until

    def mark_success(self):
        self.fail_count = 0
        self.success_count += 1
        self.cooldown_until = 0.0

    def mark_fail(self, cooldown_secs: float = 60.0):
        self.fail_count += 1
        # 指数退避：每次失败冷却时间递增，最长 300 秒
        cooldown = min(cooldown_secs * (1.5 ** min(self.fail_count - 1, 4)), 300.0)
        self.cooldown_until = time.time() + cooldown
        logger.warning(
            f"代理 [{self.raw_url}] 请求失败 (连续失败 {self.fail_count} 次)，已自动冷却 {int(cooldown)} 秒"
        )


class BcutProxyPool:
    """专门为 B 接口 (必剪 / Bcut) 打造的代理池管理器 (单例模式)"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._nodes: List[ProxyNode] = []
        self._current_index = 0
        self._pool_lock = threading.Lock()
        self._initialized = True
        self.reload_proxies()

    def _get_config_files(self) -> List[Path]:
        """获取配置文件可能存在的路径列表"""
        candidates = []
        base = Path(__file__).resolve().parent.parent
        candidates.append(base / "whisper_config.json")
        candidates.append(base / "bcut_proxies.txt")

        # 兼容打包或父级环境
        if base.parent.is_dir():
            candidates.append(base.parent / "whisper_config.json")
            candidates.append(base.parent / "bcut_proxies.txt")

        cwd = Path.cwd()
        if (cwd / "whisper_config.json") not in candidates:
            candidates.append(cwd / "whisper_config.json")
        if (cwd / "bcut_proxies.txt") not in candidates:
            candidates.append(cwd / "bcut_proxies.txt")

        return candidates

    def reload_proxies(self) -> List[str]:
        """从 whisper_config.json 或 bcut_proxies.txt 重载代理池"""
        loaded = []

        # 1. 尝试从 whisper_config.json 读取 bcut_proxies
        for p in self._get_config_files():
            if p.name == "whisper_config.json" and p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    bcut_list = cfg.get("bcut_proxies", [])
                    if isinstance(bcut_list, list):
                        loaded.extend([str(x).strip() for x in bcut_list if str(x).strip()])
                    elif isinstance(bcut_list, str) and bcut_list.strip():
                        loaded.append(bcut_list.strip())
                except Exception as e:
                    logger.debug(f"读取 {p} 代理列表失败: {e}")

            # 2. 尝试从 bcut_proxies.txt 读取纯文本
            elif p.name == "bcut_proxies.txt" and p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                loaded.append(line)
                except Exception as e:
                    logger.debug(f"读取 {p} 失败: {e}")

        # 去重并更新内部节点
        unique_proxies = []
        seen = set()
        for px in loaded:
            norm = normalize_proxy(px)
            if norm and norm not in seen:
                seen.add(norm)
                unique_proxies.append(px)

        with self._pool_lock:
            existing_map = {n.raw_url: n for n in self._nodes}
            new_nodes = []
            for px in unique_proxies:
                if px in existing_map:
                    new_nodes.append(existing_map[px])
                else:
                    new_nodes.append(ProxyNode(px))
            self._nodes = new_nodes
            self._current_index = 0

        logger.info(f"[BcutProxyPool] 成功加载 {len(self._nodes)} 个 B 接口代理节点")
        return unique_proxies

    def get_all_raw_proxies(self) -> List[str]:
        """获取所有原始代理配置列表"""
        with self._pool_lock:
            return [n.raw_url for n in self._nodes]

    def set_proxies(self, proxy_list: List[str]):
        """在内存中重置代理列表"""
        unique_proxies = []
        seen = set()
        for px in proxy_list:
            norm = normalize_proxy(px)
            if norm and norm not in seen:
                seen.add(norm)
                unique_proxies.append(px.strip())

        with self._pool_lock:
            self._nodes = [ProxyNode(px) for px in unique_proxies]
            self._current_index = 0

    def get_proxy(self) -> Optional[Tuple[str, Dict[str, str]]]:
        """
        轮询获取下一个可用代理。
        返回元组: (raw_proxy_url, requests_proxies_dict)
        若代理池为空，返回 None（表示使用直连）
        """
        with self._pool_lock:
            if not self._nodes:
                return None

            total = len(self._nodes)
            # 1. 优先获取健康节点
            for i in range(total):
                idx = (self._current_index + i) % total
                node = self._nodes[idx]
                if node.is_available:
                    self._current_index = (idx + 1) % total
                    node.last_used = time.time()
                    return node.raw_url, to_requests_proxies(node.normalized_url)

            # 2. 如果所有节点均处于冷却期，选择最先结束冷却的节点
            best_node = min(self._nodes, key=lambda n: n.cooldown_until)
            best_node.last_used = time.time()
            return best_node.raw_url, to_requests_proxies(best_node.normalized_url)

    def report_result(self, raw_proxy_url: Optional[str], success: bool):
        """上报代理节点的请求成败"""
        if not raw_proxy_url:
            return
        with self._pool_lock:
            for node in self._nodes:
                if node.raw_url == raw_proxy_url:
                    if success:
                        node.mark_success()
                    else:
                        node.mark_fail()
                    break

    def apply_test_results(self, test_results: list):
        """将批量测试结果直接记录到内存节点状态中，标记失效节点并自动隔离冷却"""
        with self._pool_lock:
            res_map = {item[1].strip(): item[0] for item in test_results if isinstance(item, (list, tuple)) and len(item) >= 2}
            for node in self._nodes:
                if node.raw_url in res_map:
                    if res_map[node.raw_url]:
                        node.mark_success()
                    else:
                        node.mark_fail(cooldown_secs=300.0)

    @staticmethod
    def test_single_proxy(proxy_str: str, timeout: int = 6, target_type: str = "bcut") -> Tuple[bool, str]:
        """
        测试单个代理节点的连通性
        target_type: 'bcut' (测试B站接口) 或 'whisper' (测试海外API，如 api.groq.com / api.openai.com)
        """
        norm = normalize_proxy(proxy_str)
        if not norm:
            return False, "代理格式无效"

        remark = proxy_str.split('#')[1].strip() if '#' in proxy_str else ''
        tag_prefix = f"[{remark}] " if remark else ""

        proxies = to_requests_proxies(norm)

        if target_type == "whisper":
            # 测试海外 Whisper API 连通性 (连接 api.groq.com)
            test_url = "https://api.groq.com/openai/v1/models"
            try:
                start_t = time.time()
                resp = requests.get(test_url, proxies=proxies, timeout=timeout)
                elapsed_ms = int((time.time() - start_t) * 1000)
                # 即使无密钥返回 401 Unauthorized 也代表代理成功握手并触达 Groq 服务
                if resp.status_code in (200, 401):
                    return True, f"{tag_prefix}连通成功 ({elapsed_ms}ms, 正常)"
                else:
                    return False, f"{tag_prefix}HTTP {resp.status_code} 异常"
            except requests.exceptions.Timeout:
                return False, f"{tag_prefix}连接超时 (>{timeout}s)"
            except requests.exceptions.ProxyError as e:
                return False, f"{tag_prefix}握手失败: {str(e)[:45]}"
            except Exception as e:
                return False, f"{tag_prefix}网络异常: {str(e)[:45]}"

        # 默认测试 Bcut 接口
        test_url = "https://member.bilibili.com/x/bcut/rubick-interface/resource/create"
        headers = {
            'User-Agent': 'Bilibili/1.0.0 (https://www.bilibili.com)',
            'Content-Type': 'application/json'
        }
        test_payload = json.dumps({
            "type": 2,
            "name": "ping.mp3",
            "size": 1024,
            "ResourceFileType": "mp3",
            "model_id": "8"
        })
        try:
            start_t = time.time()
            resp = requests.post(test_url, data=test_payload, headers=headers, proxies=proxies, timeout=timeout)
            elapsed_ms = int((time.time() - start_t) * 1000)
            if resp.status_code == 200:
                resp_json = resp.json()
                code = resp_json.get("code")
                if code == 0:
                    return True, f"{tag_prefix}连通成功 ({elapsed_ms}ms, 正常)"
                else:
                    return False, f"{tag_prefix}B站拒绝 (code={code}): {resp_json.get('message', '')}"
            elif resp.status_code == 429:
                return False, f"{tag_prefix}B站限流 (HTTP 429)"
            else:
                return False, f"{tag_prefix}HTTP {resp.status_code} 异常"
        except requests.exceptions.Timeout:
            return False, f"{tag_prefix}连接超时 (>{timeout}s)"
        except requests.exceptions.ProxyError as e:
            return False, f"{tag_prefix}握手失败: {str(e)[:45]}"
        except Exception as e:
            return False, f"{tag_prefix}网络异常: {str(e)[:45]}"


class WhisperProxyPool:
    """专门为 Whisper 接口打造的代理池管理器 (单例模式)"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._nodes: List[ProxyNode] = []
        self._current_index = 0
        self._pool_lock = threading.Lock()
        self._initialized = True
        self.reload_proxies()

    def _get_config_files(self) -> List[Path]:
        candidates = []
        base = Path(__file__).resolve().parent.parent
        candidates.append(base / "whisper_config.json")
        if base.parent.is_dir():
            candidates.append(base.parent / "whisper_config.json")
        cwd = Path.cwd()
        if (cwd / "whisper_config.json") not in candidates:
            candidates.append(cwd / "whisper_config.json")
        return candidates

    def reload_proxies(self) -> List[str]:
        loaded = []
        for p in self._get_config_files():
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    px_list = cfg.get("whisper_proxies")
                    if px_list is None:
                        # 兼容单一 proxy 字段
                        single_p = cfg.get("proxy")
                        if single_p:
                            px_list = [single_p]
                    if isinstance(px_list, list):
                        loaded.extend([str(x).strip() for x in px_list if str(x).strip()])
                    elif isinstance(px_list, str) and px_list.strip():
                        loaded.append(px_list.strip())
                except Exception as e:
                    logger.debug(f"读取 Whisper 代理配置失败: {e}")

        unique_proxies = []
        seen = set()
        for px in loaded:
            norm = normalize_proxy(px)
            if norm and norm not in seen:
                seen.add(norm)
                unique_proxies.append(px)

        with self._pool_lock:
            self._nodes = [ProxyNode(px) for px in unique_proxies]
            self._current_index = 0

        logger.info(f"[WhisperProxyPool] 成功加载 {len(self._nodes)} 个 Whisper 代理节点")
        return unique_proxies

    def get_all_raw_proxies(self) -> List[str]:
        with self._pool_lock:
            return [n.raw_url for n in self._nodes]

    def set_proxies(self, proxy_list: List[str]):
        unique_proxies = []
        seen = set()
        for px in proxy_list:
            norm = normalize_proxy(px)
            if norm and norm not in seen:
                seen.add(norm)
                unique_proxies.append(px.strip())

        with self._pool_lock:
            self._nodes = [ProxyNode(px) for px in unique_proxies]
            self._current_index = 0

    def get_proxy(self) -> Optional[Tuple[str, Dict[str, str]]]:
        with self._pool_lock:
            if not self._nodes:
                return None
            total = len(self._nodes)
            for i in range(total):
                idx = (self._current_index + i) % total
                node = self._nodes[idx]
                if node.is_available:
                    self._current_index = (idx + 1) % total
                    node.last_used = time.time()
                    return node.raw_url, to_requests_proxies(node.normalized_url)

            best_node = min(self._nodes, key=lambda n: n.cooldown_until)
            best_node.last_used = time.time()
            return best_node.raw_url, to_requests_proxies(best_node.normalized_url)

    def report_result(self, raw_proxy_url: Optional[str], success: bool):
        if not raw_proxy_url:
            return
        with self._pool_lock:
            for node in self._nodes:
                if node.raw_url == raw_proxy_url:
                    if success:
                        node.mark_success()
                    else:
                        node.mark_fail()
                    break


# 全局单例
bcut_proxy_pool = BcutProxyPool()
whisper_proxy_pool = WhisperProxyPool()

