import React, { useState, useEffect } from 'react';
import {
  Server,
  Key,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  RotateCw,
  Save,
  Sparkles,
  Zap,
  Trash2,
  Sliders
} from 'lucide-react';
import { desktopApi } from '../../lib/desktopApi';
import { cn } from '../../lib/utils';

export function SettingsView({ onToast }) {
  const [activeTab, setActiveTab] = useState('bcut'); // 'bcut' | 'whisper' | 'system'
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Settings state
  const [bcutProxiesText, setBcutProxiesText] = useState('');
  const [testingProxies, setTestingProxies] = useState(false);
  const [testResults, setTestResults] = useState({}); // { [proxy]: { ok, message } }

  const [whisperProxiesText, setWhisperProxiesText] = useState('');
  const [testingWhisperProxies, setTestingWhisperProxies] = useState(false);
  const [whisperTestResults, setWhisperTestResults] = useState({});

  const [whisperConfig, setWhisperConfig] = useState({
    base_url: 'https://api.openai.com/v1',
    api_key: '',
    model: 'whisper-1',
    prompt: '',
    temperature: 0.0,
    threads: 3
  });

  const [systemInfo, setSystemInfo] = useState({
    ffmpeg: true,
    platform: '',
    python: ''
  });

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const cfg = await desktopApi.getConfig();
      if (cfg) {
        if (cfg.whisper) {
          const rawKey = cfg.whisper.api_key;
          const keyStr = Array.isArray(rawKey) ? rawKey.join('\n') : (rawKey || '');
          setWhisperConfig({
            base_url: cfg.whisper.base_url || 'https://api.openai.com/v1',
            api_key: keyStr,
            model: cfg.whisper.model || 'whisper-1',
            prompt: cfg.whisper.prompt || '',
            temperature: cfg.whisper.temperature ?? 0.0,
            threads: cfg.whisper.threads || 3
          });
          if (cfg.whisper.proxies && Array.isArray(cfg.whisper.proxies)) {
            setWhisperProxiesText(cfg.whisper.proxies.join('\n'));
          }
        }
        if (cfg.whisper_proxies && Array.isArray(cfg.whisper_proxies)) {
          setWhisperProxiesText(cfg.whisper_proxies.join('\n'));
        }
        if (cfg.bcut_proxies && Array.isArray(cfg.bcut_proxies)) {
          setBcutProxiesText(cfg.bcut_proxies.join('\n'));
        }
        if (cfg.system) {
          setSystemInfo(cfg.system);
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveAll = async () => {
    setSaving(true);
    try {
      const bcutProxyList = bcutProxiesText
        .split('\n')
        .map((l) => l.trim())
        .filter((l) => l && !l.startsWith('#'));

      const whisperProxyList = whisperProxiesText
        .split('\n')
        .map((l) => l.trim())
        .filter((l) => l && !l.startsWith('#'));

      const keyList = whisperConfig.api_key
        .split('\n')
        .map((k) => k.trim())
        .filter(Boolean);

      const payload = {
        whisper: {
          ...whisperConfig,
          api_key: keyList.length <= 1 ? (keyList[0] || '') : keyList,
          proxies: whisperProxyList
        },
        whisper_proxies: whisperProxyList,
        bcut_proxies: bcutProxyList
      };

      const res = await desktopApi.saveConfig(payload);
      if (res && res.ok) {
        onToast?.('配置已成功保存并立即生效！', 'success');
      } else {
        onToast?.(res?.error || '保存失败', 'error');
      }
    } catch (err) {
      onToast?.(err.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDeduplicateProxies = () => {
    const lines = bcutProxiesText.split('\n');
    const seen = new Set();
    const result = [];
    for (const l of lines) {
      const trimmed = l.trim();
      if (!trimmed) continue;
      if (trimmed.startsWith('#')) {
        result.push(trimmed);
        continue;
      }
      if (!seen.has(trimmed)) {
        seen.add(trimmed);
        result.push(trimmed);
      }
    }
    setBcutProxiesText(result.join('\n'));
    onToast?.(`已去重，剩余 ${seen.size} 个代理节点`, 'info');
  };

  const handleDeduplicateWhisperProxies = () => {
    const lines = whisperProxiesText.split('\n');
    const seen = new Set();
    const result = [];
    for (const l of lines) {
      const trimmed = l.trim();
      if (!trimmed) continue;
      if (trimmed.startsWith('#')) {
        result.push(trimmed);
        continue;
      }
      if (!seen.has(trimmed)) {
        seen.add(trimmed);
        result.push(trimmed);
      }
    }
    setWhisperProxiesText(result.join('\n'));
    onToast?.(`已去重，剩余 ${seen.size} 个 Whisper 代理节点`, 'info');
  };

  const handleTestAllProxies = async () => {
    const proxyList = bcutProxiesText
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l && !l.startsWith('#'));

    if (proxyList.length === 0) {
      onToast?.('请先在下方输入代理节点', 'error');
      return;
    }

    setTestingProxies(true);
    const newResults = {};

    for (const px of proxyList) {
      try {
        const res = await desktopApi.testSingleProxy(px, 'bcut');
        newResults[px] = res;
        setTestResults({ ...newResults });
      } catch (e) {
        newResults[px] = { ok: false, message: e.message };
        setTestResults({ ...newResults });
      }
    }
    setTestingProxies(false);
    onToast?.('全部代理节点测速完成', 'success');
  };

  const handleTestAllWhisperProxies = async () => {
    const proxyList = whisperProxiesText
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l && !l.startsWith('#'));

    if (proxyList.length === 0) {
      onToast?.('请先在下方输入 Whisper 代理节点', 'error');
      return;
    }

    setTestingWhisperProxies(true);
    const newResults = {};

    for (const px of proxyList) {
      try {
        const res = await desktopApi.testSingleProxy(px, 'whisper');
        newResults[px] = res;
        setWhisperTestResults({ ...newResults });
      } catch (e) {
        newResults[px] = { ok: false, message: e.message };
        setWhisperTestResults({ ...newResults });
      }
    }
    setTestingWhisperProxies(false);
    onToast?.('全部 Whisper 代理节点测速完成', 'success');
  };

  const proxyLines = bcutProxiesText
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#'));

  return (
    <div className="flex flex-col flex-1 h-full overflow-hidden p-6 gap-4">
      {/* Settings Header Card */}
      <div className="flex items-center justify-between p-4 rounded-2xl bg-white/[0.035] border border-white/[0.08] backdrop-blur-xl">
        <div className="flex items-center gap-1.5 p-1 rounded-xl bg-white/[0.03] border border-white/[0.06]">
          {[
            { id: 'bcut', label: 'B站必剪代理池', icon: Server },
            { id: 'whisper', label: 'Whisper 多Key池', icon: Key },
            { id: 'system', label: '系统与通用', icon: Sliders }
          ].map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-[0.78rem] font-semibold transition-all cursor-pointer",
                  activeTab === tab.id
                    ? "bg-[#FE2C55]/15 text-[#FE2C55] shadow-sm border border-[#FE2C55]/25"
                    : "text-[#7a7a8e] hover:text-[#e8e8ed] hover:bg-white/[0.03]"
                )}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        <button
          onClick={handleSaveAll}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#FE2C55] text-white hover:bg-[#ff4d73] active:scale-95 transition-all text-[0.8rem] font-bold cursor-pointer shadow-[0_6px_20px_rgba(254,44,85,0.3)] disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          {saving ? '保存中...' : '保存配置'}
        </button>
      </div>

      {/* Settings Content Area */}
      <div className="flex-1 min-h-0 rounded-2xl bg-white/[0.025] border border-white/[0.08] backdrop-blur-xl overflow-y-auto p-6">
        {activeTab === 'bcut' && (
          <div className="flex flex-col gap-6 max-w-3xl">
            {/* Top Stat Cards */}
            <div className="grid grid-cols-3 gap-3">
              <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                <span className="text-[0.68rem] text-[#7a7a8e] font-medium">配置代理节点</span>
                <div className="text-[1.2rem] font-bold text-[#e8e8ed] mt-0.5">{proxyLines.length} 个</div>
              </div>

              <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                <span className="text-[0.68rem] text-[#00d68f] font-medium">测速连通成功</span>
                <div className="text-[1.2rem] font-bold text-[#00d68f] mt-0.5">
                  {Object.values(testResults).filter((r) => r.ok).length}
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                <span className="text-[0.68rem] text-[#ff4757] font-medium">测速异常/限流</span>
                <div className="text-[1.2rem] font-bold text-[#ff4757] mt-0.5">
                  {Object.values(testResults).filter((r) => !r.ok).length}
                </div>
              </div>
            </div>

            {/* Description & Action Toolbar */}
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-[0.88rem] font-bold text-[#e8e8ed]">B 接口轮询代理池</h4>
                <p className="text-[0.72rem] text-[#7a7a8e] mt-0.5">
                  每行填写一个代理地址。支持 http、https、socks5 等协议，支持自动冷却与轮询调度。
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={handleDeduplicateProxies}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.06] text-[#9b9baa] hover:text-[#e8e8ed] hover:bg-white/[0.1] active:scale-95 transition-all text-[0.72rem] font-semibold cursor-pointer"
                >
                  清洗去重
                </button>

                <button
                  onClick={handleTestAllProxies}
                  disabled={testingProxies || proxyLines.length === 0}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#00d68f]/15 text-[#00d68f] border border-[#00d68f]/25 hover:bg-[#00d68f]/25 active:scale-95 transition-all text-[0.72rem] font-bold cursor-pointer disabled:opacity-40"
                >
                  <RotateCw className={cn("w-3.5 h-3.5", testingProxies && "animate-spin")} />
                  {testingProxies ? '正在测速...' : '一键测速全部'}
                </button>
              </div>
            </div>

            {/* Proxy Input Textarea */}
            <div className="flex flex-col gap-2">
              <textarea
                value={bcutProxiesText}
                onChange={(e) => setBcutProxiesText(e.target.value)}
                rows={10}
                placeholder="例如:&#10;http://127.0.0.1:7890&#10;socks5://127.0.0.1:10808#美国节点&#10;http://user:pass@192.168.1.100:8080"
                className="w-full p-4 rounded-xl font-mono text-[0.78rem] text-[#e8e8ed] bg-black/30 border border-white/[0.08] focus:border-[#FE2C55]/50 outline-none leading-relaxed resize-y select-text"
              />
            </div>

            {/* Test Results Feed */}
            {Object.keys(testResults).length > 0 && (
              <div className="flex flex-col gap-1.5 p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] max-h-[180px] overflow-y-auto">
                <span className="text-[0.68rem] font-bold text-[#7a7a8e] mb-1">连通性测试报告:</span>
                {Object.entries(testResults).map(([px, res]) => (
                  <div key={px} className="flex items-center justify-between text-[0.72rem] py-0.5">
                    <span className="text-[#9b9baa] truncate font-mono">{px}</span>
                    <span className={cn("shrink-0 font-medium", res.ok ? "text-[#00d68f]" : "text-[#ff4757]")}>
                      {res.message}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'whisper' && (
          <div className="flex flex-col gap-5 max-w-2xl">
            <div>
              <h4 className="text-[0.88rem] font-bold text-[#e8e8ed]">Whisper API 配置</h4>
              <p className="text-[0.72rem] text-[#7a7a8e] mt-0.5">
                支持 OpenAI 官方接口以及兼容 Groq / OneAPI / NewAPI 的第三方服务商。
              </p>
            </div>

            {/* Base URL */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[0.75rem] font-semibold text-[#9b9baa]">Base URL (接口地址)</label>
              <input
                type="text"
                value={whisperConfig.base_url}
                onChange={(e) => setWhisperConfig({ ...whisperConfig, base_url: e.target.value })}
                placeholder="https://api.openai.com/v1 或 https://api.groq.com/openai/v1"
                className="p-3 rounded-xl text-[0.8rem] text-[#e8e8ed] bg-black/30 border border-white/[0.08] focus:border-[#FE2C55]/50 outline-none"
              />
            </div>

            {/* API Keys Multi-Key Pool */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <label className="text-[0.75rem] font-semibold text-[#9b9baa]">
                  API Keys (多 Key 轮询池)
                </label>
                <span className="text-[0.68rem] text-[#7a7a8e]">每行一个 Key，多并发时自动轮流使用</span>
              </div>
              <textarea
                value={whisperConfig.api_key}
                onChange={(e) => setWhisperConfig({ ...whisperConfig, api_key: e.target.value })}
                rows={4}
                placeholder="sk-proj-xxxx...&#10;gsk_xxxx..."
                className="p-3 rounded-xl font-mono text-[0.78rem] text-[#e8e8ed] bg-black/30 border border-white/[0.08] focus:border-[#FE2C55]/50 outline-none select-text"
              />
            </div>

            {/* Model & Concurrency */}
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-[0.75rem] font-semibold text-[#9b9baa]">模型名称 (Model)</label>
                <input
                  type="text"
                  value={whisperConfig.model}
                  onChange={(e) => setWhisperConfig({ ...whisperConfig, model: e.target.value })}
                  placeholder="whisper-1 或 whisper-large-v3-turbo"
                  className="p-3 rounded-xl text-[0.8rem] text-[#e8e8ed] bg-black/30 border border-white/[0.08] focus:border-[#FE2C55]/50 outline-none"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[0.75rem] font-semibold text-[#9b9baa]">并发任务数 (Threads)</label>
                <input
                  type="number"
                  min={1}
                  max={6}
                  value={whisperConfig.threads}
                  onChange={(e) => setWhisperConfig({ ...whisperConfig, threads: Number(e.target.value) })}
                  className="p-3 rounded-xl text-[0.8rem] text-[#e8e8ed] bg-black/30 border border-white/[0.08] focus:border-[#FE2C55]/50 outline-none"
                />
              </div>
            </div>

            {/* Prompt */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[0.75rem] font-semibold text-[#9b9baa]">Prompt 引导词 (可选)</label>
              <input
                type="text"
                value={whisperConfig.prompt}
                onChange={(e) => setWhisperConfig({ ...whisperConfig, prompt: e.target.value })}
                placeholder="例如：以下是简体中文语音，带有完整标点符号。"
                className="p-3 rounded-xl text-[0.8rem] text-[#e8e8ed] bg-black/30 border border-white/[0.08] focus:border-[#FE2C55]/50 outline-none"
              />
            </div>

            {/* Whisper 代理池 (填入多个代理节点) */}
            <div className="flex flex-col gap-2 pt-2 border-t border-white/[0.06]">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <label className="text-[0.78rem] font-bold text-[#e8e8ed]">
                      Whisper 代理池
                    </label>
                    <span className="px-2 py-0.5 rounded-md bg-[#FE2C55]/15 text-[#FE2C55] text-[0.68rem] font-semibold border border-[#FE2C55]/25">
                      {whisperProxiesText.split('\n').filter((l) => l.trim() && !l.trim().startsWith('#')).length} 个节点
                    </span>
                  </div>
                  <p className="text-[0.68rem] text-[#7a7a8e] mt-0.5">
                    每行填写一个海外代理节点 (支持 http / https / socks5)。请求 Groq / OpenAI 时自动轮换并发分流。
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleDeduplicateWhisperProxies}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/[0.06] text-[#9b9baa] hover:text-[#e8e8ed] hover:bg-white/[0.1] active:scale-95 transition-all text-[0.7rem] font-semibold cursor-pointer"
                  >
                    清洗去重
                  </button>

                  <button
                    onClick={handleTestAllWhisperProxies}
                    disabled={testingWhisperProxies || !whisperProxiesText.trim()}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#00d68f]/15 text-[#00d68f] border border-[#00d68f]/25 hover:bg-[#00d68f]/25 active:scale-95 transition-all text-[0.7rem] font-bold cursor-pointer disabled:opacity-40"
                  >
                    <RotateCw className={cn("w-3.5 h-3.5", testingWhisperProxies && "animate-spin")} />
                    {testingWhisperProxies ? '正在测速...' : '一键测速全部'}
                  </button>
                </div>
              </div>

              <textarea
                value={whisperProxiesText}
                onChange={(e) => setWhisperProxiesText(e.target.value)}
                rows={5}
                placeholder="例如:&#10;socks5://user:pass@140.238.42.26:8636#美国节点&#10;http://127.0.0.1:7890&#10;socks5://127.0.0.1:10808"
                className="w-full p-3.5 rounded-xl font-mono text-[0.76rem] text-[#e8e8ed] bg-black/30 border border-white/[0.08] focus:border-[#FE2C55]/50 outline-none leading-relaxed resize-y select-text"
              />

              {/* Whisper 代理测速结果 */}
              {Object.keys(whisperTestResults).length > 0 && (
                <div className="flex flex-col gap-1.5 p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] max-h-[140px] overflow-y-auto">
                  <span className="text-[0.68rem] font-bold text-[#7a7a8e] mb-1">Whisper 代理连通性报告 (Groq / OpenAI):</span>
                  {Object.entries(whisperTestResults).map(([px, res]) => (
                    <div key={px} className="flex items-center justify-between text-[0.72rem] py-0.5">
                      <span className="text-[#9b9baa] truncate font-mono">{px}</span>
                      <span className={cn("shrink-0 font-medium", res.ok ? "text-[#00d68f]" : "text-[#ff4757]")}>
                        {res.message}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'system' && (
          <div className="flex flex-col gap-4 max-w-xl">
            <h4 className="text-[0.88rem] font-bold text-[#e8e8ed]">系统状态与环境</h4>

            <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-between">
              <div>
                <div className="text-[0.82rem] font-bold text-[#e8e8ed]">FFmpeg 媒体编解码核心</div>
                <div className="text-[0.7rem] text-[#7a7a8e] mt-0.5">用于从各类视频容器中极速抽取音频流</div>
              </div>
              <span className="flex items-center gap-1 text-[0.75rem] font-bold text-[#00d68f]">
                <CheckCircle2 className="w-4 h-4" />
                已就绪
              </span>
            </div>

            <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-between">
              <div>
                <div className="text-[0.82rem] font-bold text-[#e8e8ed]">Python 嵌入式运行时</div>
                <div className="text-[0.7rem] text-[#7a7a8e] mt-0.5">版本: {systemInfo.python || '3.10'}</div>
              </div>
              <span className="flex items-center gap-1 text-[0.75rem] font-bold text-[#00d68f]">
                <CheckCircle2 className="w-4 h-4" />
                正常
              </span>
            </div>

            <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-between">
              <div>
                <div className="text-[0.82rem] font-bold text-[#e8e8ed]">桌面渲染引擎</div>
                <div className="text-[0.7rem] text-[#7a7a8e] mt-0.5">Microsoft Edge WebView2 (Chromium)</div>
              </div>
              <span className="flex items-center gap-1 text-[0.75rem] font-bold text-[#FE2C55]">
                <Zap className="w-4 h-4" />
                硬件加速
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
