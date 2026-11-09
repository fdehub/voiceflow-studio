import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { WorkspaceView } from './components/workspace/WorkspaceView';
import { SettingsView } from './components/settings/SettingsView';
import { AboutView } from './components/about/AboutView';
import { SubtitleModal } from './components/modals/SubtitleModal';
import { desktopApi } from './lib/desktopApi';
import { CheckCircle2, AlertCircle, Info, UploadCloud } from 'lucide-react';
import { cn } from './lib/utils';

export function App() {
  const [currentView, setCurrentView] = useState('workspace'); // 'workspace' | 'settings' | 'about'
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Studio Settings
  const [engine, setEngine] = useState('Whisper');
  const [exportFormat, setExportFormat] = useState('SRT');
  const [keepAudio, setKeepAudio] = useState(false);

  // Queue of tasks
  const [tasks, setTasks] = useState([]);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const isRunningRef = useRef(false);
  isRunningRef.current = isRunning;

  // Modal & Toast & Drag
  const [modalData, setModalData] = useState(null);
  const [toast, setToast] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragCounterRef = useRef(0);

  const showToast = useCallback((message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => {
      setToast(null);
    }, 3000);
  }, []);

  // 启动时恢复上次保存的任务列表与配置
  useEffect(() => {
    let mounted = true;
    desktopApi.getWorkspaceState().then((saved) => {
      if (!mounted) return;
      if (saved && typeof saved === 'object') {
        if (saved.engine) setEngine(saved.engine);
        if (saved.exportFormat) setExportFormat(saved.exportFormat);
        if (typeof saved.keepAudio === 'boolean') setKeepAudio(saved.keepAudio);
        if (Array.isArray(saved.tasks) && saved.tasks.length > 0) {
          setTasks(saved.tasks);
        }
      }
      setIsLoaded(true);
    }).catch(() => {
      if (mounted) setIsLoaded(true);
    });
    return () => {
      mounted = false;
    };
  }, []);

  // 任务列表或设置变化时自动落盘保存
  useEffect(() => {
    if (!isLoaded) return;
    const timer = setTimeout(() => {
      desktopApi.saveWorkspaceState({
        engine,
        exportFormat,
        keepAudio,
        tasks
      });
    }, 300);
    return () => clearTimeout(timer);
  }, [isLoaded, engine, exportFormat, keepAudio, tasks]);


  // ─────────────────────────────────────────────────────────────
  // 注册全局 Native 事件监听器 (来自 Python 后端)
  // ─────────────────────────────────────────────────────────────
  useEffect(() => {
    window.__onDesktopEvent = (eventName, data) => {
      if (eventName === 'task_progress') {
        setTasks((prev) =>
          prev.map((t) => {
            if (t.id === data.taskId) {
              return {
                ...t,
                status: 'processing',
                stageMessage: data.message || '处理中...',
                progress: data.progress || 0
              };
            }
            return t;
          })
        );
      } else if (eventName === 'task_finished') {
        setTasks((prev) =>
          prev.map((t) => {
            if (t.id === data.taskId) {
              return {
                ...t,
                status: 'completed',
                progress: 100,
                stageMessage: '已完成',
                savePath: data.savePath,
                previewText: data.resultText
              };
            }
            return t;
          })
        );
      } else if (eventName === 'task_error') {
        setTasks((prev) =>
          prev.map((t) => {
            if (t.id === data.taskId) {
              return {
                ...t,
                status: 'error',
                progress: 0,
                error: data.error || '转录失败'
              };
            }
            return t;
          })
        );
      } else if (eventName === 'drag_state') {
        setIsDragging(Boolean(data));
        if (!data) {
          dragCounterRef.current = 0;
        }
      } else if (eventName === 'dropped_files') {
        setIsDragging(false);
        dragCounterRef.current = 0;
        if (Array.isArray(data) && data.length > 0) {
          appendTasks(data);
          showToast(`已成功添加 ${data.length} 个音视频任务`, 'success');
        }
      } else if (eventName === 'toast') {
        setIsDragging(false);
        dragCounterRef.current = 0;
        if (data && data.message) {
          showToast(data.message, data.type || 'info');
        }
      }
    };

    return () => {
      delete window.__onDesktopEvent;
    };
  }, [showToast]);

  // ─────────────────────────────────────────────────────────────
  // 全局拖拽支持 (Drag & Drop)
  // ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const handleDragEnter = (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'copy';
      }
      dragCounterRef.current += 1;
      setIsDragging(true);
    };

    const handleDragOver = (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'copy';
      }
    };

    const handleDragLeave = (e) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounterRef.current = Math.max(0, dragCounterRef.current - 1);
      if (
        dragCounterRef.current === 0 ||
        e.clientX <= 0 ||
        e.clientY <= 0 ||
        e.clientX >= window.innerWidth ||
        e.clientY >= window.innerHeight
      ) {
        dragCounterRef.current = 0;
        setIsDragging(false);
      }
    };

    const handleDrop = async (e) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounterRef.current = 0;
      setIsDragging(false);

      if (!e.dataTransfer || !e.dataTransfer.files || e.dataTransfer.files.length === 0) {
        return;
      }

      const fileMetas = Array.from(e.dataTransfer.files).map((f) => ({
        name: f.name,
        size: f.size,
        lastModified: f.lastModified,
        type: f.type,
        path: f.path || f.pywebviewFullPath || ''
      }));

      try {
        const resolved = await desktopApi.resolveDroppedFiles(fileMetas);
        if (resolved && resolved.length > 0) {
          appendTasks(resolved);
          showToast(`已成功添加 ${resolved.length} 个音视频任务`, 'success');
        } else {
          showToast('未检测到支持的音视频格式文件', 'warning');
        }
      } catch (err) {
        console.error('Failed to resolve dropped files:', err);
        showToast('读取拖入文件失败', 'error');
      }
    };

    const handleDragEnd = (e) => {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      dragCounterRef.current = 0;
      setIsDragging(false);
    };

    window.addEventListener('dragenter', handleDragEnter, true);
    window.addEventListener('dragover', handleDragOver, true);
    window.addEventListener('dragleave', handleDragLeave, true);
    window.addEventListener('drop', handleDrop, true);
    window.addEventListener('dragend', handleDragEnd, true);

    return () => {
      window.removeEventListener('dragenter', handleDragEnter, true);
      window.removeEventListener('dragover', handleDragOver, true);
      window.removeEventListener('dragleave', handleDragLeave, true);
      window.removeEventListener('drop', handleDrop, true);
      window.removeEventListener('dragend', handleDragEnd, true);
    };
  }, []);

  // ─────────────────────────────────────────────────────────────
  // 任务增删管理
  // ─────────────────────────────────────────────────────────────
  const appendTasks = (items) => {
    setTasks((prev) => {
      const existingPaths = new Set(prev.map((t) => t.path));
      const newTasks = [];
      for (const item of items) {
        if (!existingPaths.has(item.path)) {
          const isDone = Boolean(item.completed);
          newTasks.push({
            id: `task_${Date.now()}_${Math.random().toString(36).substr(2, 7)}`,
            path: item.path,
            name: item.name,
            dir: item.dir,
            size: item.size,
            isVideo: item.isVideo,
            ext: item.ext,
            status: isDone ? 'completed' : 'pending',
            progress: isDone ? 100 : 0,
            stageMessage: isDone ? '已完成' : '',
            savePath: item.savePath || null,
            error: null
          });
        }
      }
      return [...prev, ...newTasks];
    });
  };

  const handleAddFiles = async () => {
    try {
      const files = await desktopApi.selectFiles();
      if (files && files.length > 0) {
        appendTasks(files);
        showToast(`已添加 ${files.length} 个文件`, 'success');
      }
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const handleAddFolder = async () => {
    try {
      const files = await desktopApi.selectFolder();
      if (files && files.length > 0) {
        appendTasks(files);
        showToast(`从文件夹导入 ${files.length} 个媒体文件`, 'success');
      } else {
        showToast('文件夹内未找到支持的音视频文件', 'info');
      }
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const handleClearQueue = () => {
    if (isRunning) {
      showToast('请先停止转录再清空列表', 'error');
      return;
    }
    setTasks([]);
  };

  const handleRemoveTask = (taskId) => {
    setTasks((prev) => prev.filter((t) => t.id !== taskId));
  };

  const handleRetryTask = (taskId) => {
    setTasks((prev) =>
      prev.map((t) => (t.id === taskId ? { ...t, status: 'pending', error: null, progress: 0 } : t))
    );
  };

  const handleRetryFailed = () => {
    setTasks((prev) =>
      prev.map((t) => (t.status === 'error' ? { ...t, status: 'pending', error: null, progress: 0 } : t))
    );
  };

  // ─────────────────────────────────────────────────────────────
  // 批量调度引擎 (调度 pending 任务)
  // ─────────────────────────────────────────────────────────────
  const runNextTasks = useCallback(async () => {
    if (!isRunningRef.current) return;

    // 寻找待处理的任务
    setTasks((latestTasks) => {
      const pendingTask = latestTasks.find((t) => t.status === 'pending');
      if (!pendingTask) {
        // 如果没有 pending 且没有 processing，说明全部完成
        const stillProcessing = latestTasks.some((t) => t.status === 'processing');
        if (!stillProcessing) {
          setIsRunning(false);
          showToast('全部任务已处理完成！', 'success');
        }
        return latestTasks;
      }

      // 触发单个任务转录
      desktopApi.startTask(
        pendingTask.id,
        pendingTask.path,
        engine,
        exportFormat,
        keepAudio
      );

      return latestTasks.map((t) =>
        t.id === pendingTask.id ? { ...t, status: 'processing', stageMessage: '准备中...' } : t
      );
    });
  }, [engine, exportFormat, keepAudio, showToast]);

  // 当任务状态改变时，若处于运行态则持续调度后续任务
  useEffect(() => {
    if (isRunning) {
      const timer = setTimeout(() => {
        runNextTasks();
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [tasks, isRunning, runNextTasks]);

  const handleStartAll = () => {
    const hasPendingOrError = tasks.some((t) => t.status === 'pending' || t.status === 'error');
    if (!hasPendingOrError) {
      // 如果所有都已完成，把所有重置为 pending
      setTasks((prev) => prev.map((t) => ({ ...t, status: 'pending', progress: 0, error: null })));
    }
    setIsRunning(true);
    showToast('已开始批量转录', 'info');
  };

  const handleStopAll = () => {
    setIsRunning(false);
    showToast('已停止全部转录任务', 'info');
  };

  const handleFastExportTxt = async () => {
    if (tasks.length === 0) return;
    let successCount = 0;
    for (const t of tasks) {
      const res = await desktopApi.fastExportTxt(t.path);
      if (res && res.ok) {
        successCount++;
      }
    }
    if (successCount > 0) {
      showToast(`成功极速导出 ${successCount} 个 TXT 纯文本文档！`, 'success');
    } else {
      showToast('未检测到同名已生成的字幕文件', 'info');
    }
  };

  // ─────────────────────────────────────────────────────────────
  // 辅助功能
  // ─────────────────────────────────────────────────────────────
  const handleOpenFolder = async (filePath) => {
    await desktopApi.openInFolder(filePath);
  };

  const handlePreviewTask = async (task) => {
    const res = await desktopApi.readSubtitleContent(task.path, exportFormat);
    if (res && res.ok) {
      setModalData({
        name: task.name,
        path: res.path,
        content: res.content
      });
    } else {
      showToast(res?.error || '无法读取字幕内容', 'error');
    }
  };

  const handleCopyTaskText = async (task) => {
    const res = await desktopApi.readSubtitleContent(task.path, 'txt');
    if (res && res.ok && res.content) {
      navigator.clipboard.writeText(res.content);
      showToast('已复制识别文本到剪贴板', 'success');
    } else {
      const srtRes = await desktopApi.readSubtitleContent(task.path, 'srt');
      if (srtRes && srtRes.ok && srtRes.content) {
        navigator.clipboard.writeText(srtRes.content);
        showToast('已复制字幕内容到剪贴板', 'success');
      } else {
        showToast('未找到可复制的字幕或文本文件', 'error');
      }
    }
  };

  const activeTaskCount = tasks.filter((t) => t.status === 'processing' || t.status === 'pending').length;

  return (
    <div className="flex w-screen h-screen overflow-hidden bg-[#0e0e14] text-[#e8e8ed] select-none">
      {/* Sidebar */}
      <Sidebar
        currentView={currentView}
        onViewChange={setCurrentView}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapsed={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
        engine={engine}
        taskCounts={{ active: activeTaskCount }}
      />

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0 h-full overflow-hidden bg-[#0e0e14]">
        {currentView === 'workspace' && (
          <WorkspaceView
            tasks={tasks}
            engine={engine}
            onEngineChange={setEngine}
            exportFormat={exportFormat}
            onFormatChange={setExportFormat}
            keepAudio={keepAudio}
            onKeepAudioChange={setKeepAudio}
            onAddFiles={handleAddFiles}
            onAddFolder={handleAddFolder}
            onClearQueue={handleClearQueue}
            onFastExportTxt={handleFastExportTxt}
            onStartAll={handleStartAll}
            onStopAll={handleStopAll}
            onRetryTask={handleRetryTask}
            onRetryFailed={handleRetryFailed}
            onRemoveTask={handleRemoveTask}
            onOpenFolder={handleOpenFolder}
            onPreviewTask={handlePreviewTask}
            onCopyTaskText={handleCopyTaskText}
            isRunning={isRunning}
          />
        )}

        {currentView === 'settings' && <SettingsView onToast={showToast} />}

        {currentView === 'about' && <AboutView onToast={showToast} />}
      </main>

      {/* Subtitle Preview Modal */}
      {modalData && (
        <SubtitleModal
          modalData={modalData}
          onClose={() => setModalData(null)}
          onOpenFolder={handleOpenFolder}
        />
      )}

      {/* 全局拖拽悬停视觉指示层 */}
      {isDragging && (
        <div className="fixed inset-0 z-50 pointer-events-none border-2 border-dashed border-[#FE2C55] bg-[#FE2C55]/[0.06] backdrop-blur-[2px] flex items-center justify-center transition-all animate-in fade-in duration-150">
          <div className="px-6 py-3.5 rounded-2xl bg-[#16161e]/95 border border-[#FE2C55]/40 text-white font-bold text-sm shadow-[0_16px_40px_rgba(0,0,0,0.6)] flex items-center gap-3">
            <UploadCloud className="w-5 h-5 text-[#FE2C55] animate-bounce" />
            释放鼠标即可添加音视频文件或文件夹
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-[#16161e]/90 border border-white/[0.12] text-white text-[0.8rem] font-semibold shadow-[0_16px_40px_rgba(0,0,0,0.5)] backdrop-blur-xl animate-in fade-in slide-in-from-bottom-2 duration-200">
          {toast.type === 'success' && <CheckCircle2 className="w-4 h-4 text-[#00d68f]" />}
          {toast.type === 'error' && <AlertCircle className="w-4 h-4 text-[#ff4757]" />}
          {toast.type === 'warning' && <AlertCircle className="w-4 h-4 text-[#ffa502]" />}
          {toast.type === 'info' && <Info className="w-4 h-4 text-[#7c5cfc]" />}
          <span>{toast.message}</span>
        </div>
      )}
    </div>
  );
}

export default App;
