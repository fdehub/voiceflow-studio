import React, { memo } from 'react';
import {
  FolderOpen,
  Eye,
  Copy,
  RotateCw,
  X,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Clock,
  Video,
  Music
} from 'lucide-react';
import { cn, formatBytes } from '../../lib/utils';

export const TaskCard = memo(function TaskCard({
  task,
  onOpenFolder,
  onPreview,
  onCopyText,
  onRetry,
  onRemove
}) {
  const isVideo = task.isVideo ?? true;
  const status = task.status || 'pending';

  return (
    <div
      className={cn(
        "group relative flex flex-col gap-2.5 p-3.5 rounded-xl border transition-all duration-150 ease-out select-none",
        status === 'completed'
          ? "bg-[#00d68f]/[0.035] border-[#00d68f]/20 hover:border-[#00d68f]/30"
          : status === 'error'
          ? "bg-[#ff4757]/[0.035] border-[#ff4757]/20 hover:border-[#ff4757]/30"
          : status === 'processing'
          ? "bg-[#FE2C55]/[0.035] border-[#FE2C55]/25 shadow-[0_4px_20px_rgba(254,44,85,0.06)]"
          : "bg-white/[0.025] border-white/[0.07] hover:bg-white/[0.045] hover:border-white/[0.12]"
      )}
    >
      <div className="flex items-start gap-3">
        {/* Media Type Icon Badge */}
        <div
          className={cn(
            "flex items-center justify-center w-8 h-8 rounded-lg shrink-0 text-[0.72rem] font-bold",
            isVideo
              ? "bg-[#FE2C55]/15 text-[#FE2C55] border border-[#FE2C55]/25"
              : "bg-[#7c5cfc]/15 text-[#9b7ffc] border border-[#7c5cfc]/25"
          )}
          title={isVideo ? "视频文件" : "音频文件"}
        >
          {isVideo ? '视' : '音'}
        </div>

        {/* File Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className="text-[0.84rem] font-semibold text-[#e8e8ed] truncate flex-1 leading-snug"
              title={task.path}
            >
              {task.name}
            </span>

            {/* Status Capsule */}
            {status === 'completed' && (
              <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[0.7rem] font-bold bg-[#00d68f]/15 text-[#00d68f] border border-[#00d68f]/25 shrink-0">
                <CheckCircle2 className="w-3 h-3" />
                已完成
              </span>
            )}

            {status === 'error' && (
              <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[0.7rem] font-bold bg-[#ff4757]/15 text-[#ff4757] border border-[#ff4757]/25 shrink-0" title={task.error}>
                <AlertCircle className="w-3 h-3" />
                失败
              </span>
            )}

            {status === 'processing' && (
              <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[0.7rem] font-bold bg-[#FE2C55]/15 text-[#FE2C55] border border-[#FE2C55]/25 shrink-0">
                <Loader2 className="w-3 h-3 animate-spin" />
                {task.stageMessage || `${task.progress || 0}%`}
              </span>
            )}

            {status === 'pending' && (
              <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[0.7rem] font-semibold bg-white/[0.06] text-[#9b9baa] border border-white/[0.08] shrink-0">
                <Clock className="w-3 h-3" />
                等待中
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 text-[0.7rem] text-[#7a7a8e] truncate">
            <span>{formatBytes(task.size)}</span>
            <span>·</span>
            <span className="truncate max-w-[400px]" title={task.dir}>
              {task.dir}
            </span>
            {task.error && (
              <>
                <span>·</span>
                <span className="text-[#ff4757] truncate font-medium">{task.error}</span>
              </>
            )}
          </div>
        </div>

        {/* Action Toolbar */}
        <div className="flex items-center gap-1 shrink-0">
          {status === 'completed' && (
            <>
              <button
                onClick={() => onPreview(task)}
                title="预览识别结果"
                className="flex items-center justify-center w-7 h-7 rounded-lg text-[#9b9baa] hover:text-[#e8e8ed] hover:bg-white/[0.08] active:scale-95 transition-all cursor-pointer"
              >
                <Eye className="w-3.5 h-3.5" />
              </button>

              <button
                onClick={() => onCopyText(task)}
                title="复制识别文本"
                className="flex items-center justify-center w-7 h-7 rounded-lg text-[#9b9baa] hover:text-[#e8e8ed] hover:bg-white/[0.08] active:scale-95 transition-all cursor-pointer"
              >
                <Copy className="w-3.5 h-3.5" />
              </button>
            </>
          )}

          <button
            onClick={() => onOpenFolder(task.path)}
            title="在文件夹中显示"
            className="flex items-center justify-center w-7 h-7 rounded-lg text-[#9b9baa] hover:text-[#e8e8ed] hover:bg-white/[0.08] active:scale-95 transition-all cursor-pointer"
          >
            <FolderOpen className="w-3.5 h-3.5" />
          </button>

          {(status === 'error' || status === 'completed') && (
            <button
              onClick={() => onRetry(task.id)}
              title="重新转录"
              className="flex items-center justify-center w-7 h-7 rounded-lg text-[#9b9baa] hover:text-[#FE2C55] hover:bg-[#FE2C55]/10 active:scale-95 transition-all cursor-pointer"
            >
              <RotateCw className="w-3.5 h-3.5" />
            </button>
          )}

          {status !== 'processing' && (
            <button
              onClick={() => onRemove(task.id)}
              title="从列表中移除"
              className="flex items-center justify-center w-7 h-7 rounded-lg text-[#7a7a8e] hover:text-[#ff4757] hover:bg-[#ff4757]/10 active:scale-95 transition-all cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Progress Bar for Active / Processing Tasks */}
      {status === 'processing' && (
        <div className="w-full h-1 bg-white/[0.08] rounded-full overflow-hidden mt-1">
          <div
            className="h-full bg-gradient-to-r from-[#FE2C55] to-[#ff4d73] transition-all duration-300 rounded-full"
            style={{ width: `${Math.max(5, task.progress || 0)}%` }}
          />
        </div>
      )}
    </div>
  );
});
