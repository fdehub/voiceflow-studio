import React from 'react';
import { Sparkles } from 'lucide-react';

export function AboutView() {
  return (
    <div className="flex flex-col flex-1 h-full overflow-hidden p-6 gap-4">
      <div className="flex flex-col items-center justify-center flex-1 max-w-xl mx-auto text-center p-8 rounded-2xl bg-white/[0.025] border border-white/[0.08] backdrop-blur-xl">
        {/* Brand Icon */}
        <div className="flex items-center justify-center w-20 h-20 rounded-3xl bg-gradient-to-br from-[#FE2C55] to-[#ff4757] shadow-[0_12px_36px_rgba(254,44,85,0.35)] mb-5">
          <Sparkles className="w-10 h-10 text-white" />
        </div>

        <h2 className="text-[1.35rem] font-bold text-[#e8e8ed] mb-4">
          音流 (VoiceFlow Studio) · 多引擎并发 AI 语音识别工作台
        </h2>

        <p className="text-[0.82rem] text-[#7a7a8e] max-w-md leading-relaxed">
          专为音视频创作者打造的本地音视频转字幕利器。
          支持 B站必剪 (带代理池自动冷却)、剪映接口及 OpenAI Whisper 多Key轮询池。
          0秒提取现有字幕，极速批处理，高效流转，声落成文。
        </p>
      </div>
    </div>
  );
}
