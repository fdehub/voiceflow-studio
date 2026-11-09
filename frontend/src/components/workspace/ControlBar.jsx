import React from 'react';
import {
  Plus,
  FolderPlus,
  Trash2,
  Play,
  Square,
  RotateCw,
  FileText,
  Volume2
} from 'lucide-react';
import { cn } from '../../lib/utils';

export function ControlBar({
  engine,
  onEngineChange,
  exportFormat,
  onFormatChange,
  keepAudio,
  onKeepAudioChange,
  onAddFiles,
  onAddFolder,
  onClearQueue,
  onFastExportTxt,
  onStartAll,
  onStopAll,
  onRetryFailed,
  isRunning,
  totalTasks,
  pendingCount,
  failedCount
}) {
  const engineOptions = [
    { id: 'B 接口', label: 'B站必剪 (快速免费)' },
    { id: 'J 接口', label: '剪映接口 (备用)' },
    { id: 'Whisper', label: 'Whisper API (高精度)' }
  ];

  const formatOptions = ['SRT', 'TXT', 'ASS', 'VTT', 'LRC', 'JSON'];

  return (
    <div className="flex flex-col gap-3 p-4 rounded-2xl bg-white/[0.035] border border-white/[0.08] backdrop-blur-xl">
      {/* Top Row: Engine, Format, Audio switch */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Engine Selector */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/[0.04] border border-white/[0.08]">
            <span className="text-[0.72rem] font-medium text-[#7a7a8e]">引擎:</span>
            <select
              value={engine}
              onChange={(e) => onEngineChange(e.target.value)}
              className="bg-transparent text-[0.78rem] font-semibold text-[#e8e8ed] outline-none cursor-pointer"
            >
              {engineOptions.map((opt) => (
                <option key={opt.id} value={opt.id} className="bg-[#16161e] text-[#e8e8ed]">
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Format Selector */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/[0.04] border border-white/[0.08]">
            <span className="text-[0.72rem] font-medium text-[#7a7a8e]">导出:</span>
            <select
              value={exportFormat}
              onChange={(e) => onFormatChange(e.target.value)}
              className="bg-transparent text-[0.78rem] font-semibold text-[#e8e8ed] outline-none cursor-pointer uppercase"
            >
              {formatOptions.map((fmt) => (
                <option key={fmt} value={fmt} className="bg-[#16161e] text-[#e8e8ed]">
                  {fmt} 字幕
                </option>
              ))}
            </select>
          </div>

          {/* Keep Audio Toggle */}
          <label className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-white/[0.04] border border-white/[0.08] cursor-pointer hover:bg-white/[0.06] transition-colors select-none">
            <input
              type="checkbox"
              checked={keepAudio}
              onChange={(e) => onKeepAudioChange(e.target.checked)}
              className="w-3.5 h-3.5 rounded accent-[#FE2C55] cursor-pointer"
            />
            <Volume2 className="w-3.5 h-3.5 text-[#9b9baa]" />
            <span className="text-[0.75rem] font-medium text-[#9b9baa]">保留转换 MP3</span>
          </label>
        </div>

        {/* Primary Action Button */}
        <div className="flex items-center gap-2">
          {failedCount > 0 && !isRunning && (
            <button
              onClick={onRetryFailed}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#ff4757]/15 text-[#ff4757] border border-[#ff4757]/30 hover:bg-[#ff4757]/25 active:scale-95 transition-all text-[0.78rem] font-semibold cursor-pointer shadow-[0_4px_16px_rgba(255,71,87,0.12)]"
            >
              <RotateCw className="w-3.5 h-3.5" />
              重试失败 ({failedCount})
            </button>
          )}

          {isRunning ? (
            <button
              onClick={onStopAll}
              className="flex items-center gap-2 px-5 py-2 rounded-xl bg-[#ff4757] text-white hover:bg-[#ff4757]/90 active:scale-95 transition-all text-[0.82rem] font-bold cursor-pointer shadow-[0_6px_20px_rgba(255,71,87,0.3)]"
            >
              <Square className="w-4 h-4 fill-white" />
              停止全部
            </button>
          ) : (
            <button
              onClick={onStartAll}
              disabled={totalTasks === 0}
              className={cn(
                "flex items-center gap-2 px-5 py-2 rounded-xl text-white transition-all text-[0.82rem] font-bold cursor-pointer select-none",
                totalTasks > 0
                  ? "bg-gradient-to-r from-[#FE2C55] to-[#ff4d73] hover:brightness-110 active:scale-95 shadow-[0_8px_24px_rgba(254,44,85,0.35)]"
                  : "bg-white/10 text-white/40 cursor-not-allowed"
              )}
            >
              <Play className="w-4 h-4 fill-white" />
              {pendingCount > 0 ? `开始转录 (${pendingCount} 项)` : '全部开始'}
            </button>
          )}
        </div>
      </div>

      {/* Bottom Row: File additions, clear, fast txt */}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-white/[0.04]">
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={onAddFiles}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.06] text-[#e8e8ed] hover:bg-white/[0.1] active:scale-95 transition-all text-[0.75rem] font-semibold cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5 text-[#FE2C55]" />
            添加媒体文件
          </button>

          <button
            onClick={onAddFolder}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.06] text-[#e8e8ed] hover:bg-white/[0.1] active:scale-95 transition-all text-[0.75rem] font-semibold cursor-pointer"
          >
            <FolderPlus className="w-3.5 h-3.5 text-[#7c5cfc]" />
            导入文件夹
          </button>

          <button
            onClick={onFastExportTxt}
            disabled={totalTasks === 0}
            title="对已存在字幕的文件极速导出 TXT 纯文本"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.04] text-[#9b9baa] hover:text-[#e8e8ed] hover:bg-white/[0.08] active:scale-95 transition-all text-[0.75rem] font-semibold cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <FileText className="w-3.5 h-3.5" />
            快速导出 TXT
          </button>
        </div>

        {totalTasks > 0 && (
          <button
            onClick={onClearQueue}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[#7a7a8e] hover:text-[#ff4757] hover:bg-[#ff4757]/10 active:scale-95 transition-all text-[0.72rem] font-medium cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            清空列表
          </button>
        )}
      </div>
    </div>
  );
}
