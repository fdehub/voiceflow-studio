import React from 'react';
import { UploadCloud, Plus, FolderPlus } from 'lucide-react';

export function EmptyDropzone({ onAddFiles, onAddFolder }) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 min-h-[340px] p-8 rounded-2xl border-2 border-dashed border-white/[0.1] bg-white/[0.015] hover:bg-white/[0.03] hover:border-[#FE2C55]/40 transition-all duration-200 select-none">
      <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-white/[0.04] border border-white/[0.08] mb-4 text-[#9b9baa] shadow-[0_8px_24px_rgba(0,0,0,0.2)]">
        <UploadCloud className="w-8 h-8 text-[#FE2C55]" />
      </div>

      <h3 className="text-[1.05rem] font-bold text-[#e8e8ed] mb-1.5">
        拖拽音视频文件或文件夹至此处
      </h3>

      <p className="text-[0.78rem] text-[#7a7a8e] text-center max-w-md mb-6 leading-relaxed">
        支持 MP4 · MKV · MOV · AVI · FLV · TS · MP3 · WAV · M4A · FLAC 等主流格式
        <br />
        已存在同名字幕时将自动秒速导出
      </p>

      <div className="flex items-center gap-3">
        <button
          onClick={onAddFiles}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/[0.07] text-[#e8e8ed] hover:bg-white/[0.12] active:scale-95 transition-all text-[0.8rem] font-semibold cursor-pointer shadow-[0_4px_16px_rgba(0,0,0,0.15)]"
        >
          <Plus className="w-4 h-4 text-[#FE2C55]" />
          选取媒体文件
        </button>

        <button
          onClick={onAddFolder}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/[0.07] text-[#e8e8ed] hover:bg-white/[0.12] active:scale-95 transition-all text-[0.8rem] font-semibold cursor-pointer shadow-[0_4px_16px_rgba(0,0,0,0.15)]"
        >
          <FolderPlus className="w-4 h-4 text-[#7c5cfc]" />
          导入整个文件夹
        </button>
      </div>
    </div>
  );
}
