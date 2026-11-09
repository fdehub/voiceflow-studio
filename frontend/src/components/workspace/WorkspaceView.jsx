import React, { useState, useMemo } from 'react';
import { ControlBar } from './ControlBar';
import { TaskCard } from './TaskCard';
import { EmptyDropzone } from './EmptyDropzone';
import { Search } from 'lucide-react';
import { cn } from '../../lib/utils';

export function WorkspaceView({
  tasks,
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
  onRetryTask,
  onRetryFailed,
  onRemoveTask,
  onOpenFolder,
  onPreviewTask,
  onCopyTaskText,
  isRunning
}) {
  const [filterTab, setFilterTab] = useState('all'); // 'all' | 'processing' | 'completed' | 'error'
  const [searchQuery, setSearchQuery] = useState('');

  // Counts
  const counts = useMemo(() => {
    let pending = 0;
    let processing = 0;
    let completed = 0;
    let error = 0;
    tasks.forEach((t) => {
      if (t.status === 'processing') processing++;
      else if (t.status === 'completed') completed++;
      else if (t.status === 'error') error++;
      else pending++;
    });
    return {
      total: tasks.length,
      pending,
      processing,
      completed,
      error,
      active: processing + pending
    };
  }, [tasks]);

  // Filtered tasks
  const filteredTasks = useMemo(() => {
    return tasks.filter((t) => {
      // Tab filter
      if (filterTab === 'processing' && t.status !== 'processing' && t.status !== 'pending') return false;
      if (filterTab === 'completed' && t.status !== 'completed') return false;
      if (filterTab === 'error' && t.status !== 'error') return false;

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const nameMatch = (t.name || '').toLowerCase().includes(q);
        const dirMatch = (t.dir || '').toLowerCase().includes(q);
        return nameMatch || dirMatch;
      }
      return true;
    });
  }, [tasks, filterTab, searchQuery]);

  return (
    <div className="flex flex-col flex-1 h-full overflow-hidden p-6 gap-4">
      {/* Studio Control Bar */}
      <ControlBar
        engine={engine}
        onEngineChange={onEngineChange}
        exportFormat={exportFormat}
        onFormatChange={onFormatChange}
        keepAudio={keepAudio}
        onKeepAudioChange={onKeepAudioChange}
        onAddFiles={onAddFiles}
        onAddFolder={onAddFolder}
        onClearQueue={onClearQueue}
        onFastExportTxt={onFastExportTxt}
        onStartAll={onStartAll}
        onStopAll={onStopAll}
        onRetryFailed={onRetryFailed}
        isRunning={isRunning}
        totalTasks={tasks.length}
        pendingCount={counts.pending}
        failedCount={counts.error}
      />

      {/* Main Viewport Card */}
      <div className="flex flex-col flex-1 min-h-0 rounded-2xl bg-white/[0.025] border border-white/[0.08] backdrop-blur-xl overflow-hidden p-4">
        {/* Header toolbar: Filter tabs + Search */}
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 mb-3 border-b border-white/[0.06]">
          <div className="flex items-center gap-1 p-1 rounded-xl bg-white/[0.03] border border-white/[0.06]">
            {[
              { id: 'all', label: '全部', count: counts.total },
              { id: 'processing', label: '进行中', count: counts.processing + counts.pending },
              { id: 'completed', label: '已完成', count: counts.completed },
              { id: 'error', label: '失败', count: counts.error },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setFilterTab(tab.id)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1 rounded-lg text-[0.75rem] font-semibold transition-all cursor-pointer",
                  filterTab === tab.id
                    ? "bg-white/[0.1] text-white shadow-sm"
                    : "text-[#7a7a8e] hover:text-[#e8e8ed] hover:bg-white/[0.03]"
                )}
              >
                <span>{tab.label}</span>
                <span className={cn(
                  "px-1.5 py-0.2 rounded-full text-[0.65rem]",
                  filterTab === tab.id ? "bg-[#FE2C55]/20 text-[#FE2C55]" : "bg-white/[0.06] text-[#7a7a8e]"
                )}>
                  {tab.count}
                </span>
              </button>
            ))}
          </div>

          {/* Search Box */}
          {tasks.length > 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-white/[0.04] border border-white/[0.08] w-[220px]">
              <Search className="w-3.5 h-3.5 text-[#7a7a8e]" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="搜索任务名称或路径..."
                className="bg-transparent text-[0.75rem] text-[#e8e8ed] placeholder-[#7a7a8e] outline-none w-full"
              />
            </div>
          )}
        </div>

        {/* Task List or Empty Dropzone */}
        {tasks.length === 0 ? (
          <EmptyDropzone onAddFiles={onAddFiles} onAddFolder={onAddFolder} />
        ) : filteredTasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center flex-1 text-[#7a7a8e] text-[0.8rem]">
            未匹配到相关任务
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto pr-1 space-y-2">
            {filteredTasks.map((t) => (
              <TaskCard
                key={t.id}
                task={t}
                onOpenFolder={onOpenFolder}
                onPreview={onPreviewTask}
                onCopyText={onCopyTaskText}
                onRetry={onRetryTask}
                onRemove={onRemoveTask}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
