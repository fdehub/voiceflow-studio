import React, { useState } from 'react';
import { X, Copy, Check, FolderOpen, FileText } from 'lucide-react';

export function SubtitleModal({ modalData, onClose, onOpenFolder }) {
  const [copied, setCopied] = useState(false);

  if (!modalData) return null;

  const handleCopy = () => {
    if (modalData.content) {
      navigator.clipboard.writeText(modalData.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/60 backdrop-blur-md animate-in fade-in duration-200">
      <div className="flex flex-col w-full max-w-2xl max-h-[85vh] rounded-2xl bg-[#16161e] border border-white/[0.1] shadow-[0_24px_64px_rgba(0,0,0,0.5)] overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.08] bg-white/[0.02]">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-[#FE2C55]/15 text-[#FE2C55] shrink-0">
              <FileText className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <h3 className="text-[0.92rem] font-bold text-[#e8e8ed] truncate">
                {modalData.name || '字幕预览'}
              </h3>
              <p className="text-[0.68rem] text-[#7a7a8e] truncate" title={modalData.path}>
                {modalData.path}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="flex items-center justify-center w-8 h-8 rounded-lg text-[#7a7a8e] hover:text-[#e8e8ed] hover:bg-white/[0.08] active:scale-95 transition-all cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body / Text Content */}
        <div className="flex-1 p-5 overflow-y-auto bg-black/20">
          <pre className="font-mono text-[0.8rem] text-[#e8e8ed]/90 whitespace-pre-wrap break-words leading-relaxed select-text">
            {modalData.content || '暂无内容'}
          </pre>
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-white/[0.08] bg-white/[0.02]">
          <span className="text-[0.7rem] text-[#7a7a8e]">
            共 {modalData.content ? modalData.content.length : 0} 字符
          </span>

          <div className="flex items-center gap-2">
            <button
              onClick={() => onOpenFolder(modalData.path)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/[0.06] text-[#e8e8ed] hover:bg-white/[0.1] active:scale-95 transition-all text-[0.78rem] font-semibold cursor-pointer"
            >
              <FolderOpen className="w-3.5 h-3.5 text-[#9b9baa]" />
              打开目录
            </button>

            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-[#FE2C55] text-white hover:bg-[#ff4d73] active:scale-95 transition-all text-[0.78rem] font-bold cursor-pointer shadow-[0_4px_16px_rgba(254,44,85,0.25)]"
            >
              {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? '已复制' : '复制全文'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
