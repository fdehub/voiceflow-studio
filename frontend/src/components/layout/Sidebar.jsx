import React from 'react';
import {
  Mic,
  Settings,
  Info,
  PanelLeftClose,
  PanelLeftOpen,
  Sparkles,
  Zap
} from 'lucide-react';
import { cn } from '../../lib/utils';

export function Sidebar({
  currentView,
  onViewChange,
  isCollapsed,
  onToggleCollapsed,
  engine,
  taskCounts
}) {
  const navItems = [
    { id: 'workspace', label: '转录工作台', icon: Mic, badge: taskCounts.active > 0 ? taskCounts.active : null },
    { id: 'settings', label: '接口设置', icon: Settings },
    { id: 'about', label: '关于软件', icon: Info },
  ];

  return (
    <aside
      className={cn(
        "relative flex flex-col shrink-0 border-r border-white/[0.08] bg-[#0e0e14] transition-all duration-300 ease-[cubic-bezier(0.2,0,0,1)] z-20 select-none",
        isCollapsed ? "w-[68px]" : "w-[220px]"
      )}
    >
      {/* Brand Header */}
      <div className={cn("flex items-center h-16 px-4 gap-3", isCollapsed && "justify-center px-0")}>
        <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-[#FE2C55] to-[#ff4757] shadow-[0_8px_20px_rgba(254,44,85,0.25)] shrink-0">
          <Sparkles className="w-5 h-5 text-white" />
        </div>

        {!isCollapsed && (
          <div className="flex flex-col min-w-0 overflow-hidden">
            <span className="text-[0.98rem] font-bold tracking-wide text-[#e8e8ed] truncate">
              音流 VoiceFlow
            </span>
            <span className="text-[0.66rem] font-medium text-[#7a7a8e] truncate">
              多引擎并发 AI 字幕工作台
            </span>
          </div>
        )}
      </div>

      {/* Navigation List */}
      <nav className="flex-1 flex flex-col gap-1.5 px-3 py-4">
        <div className={cn("flex items-center mb-2 px-1", isCollapsed ? "justify-center" : "justify-between")}>
          {!isCollapsed && (
            <span className="text-[0.65rem] font-bold uppercase tracking-wider text-[#7a7a8e]">
              导航
            </span>
          )}
          <button
            type="button"
            onClick={onToggleCollapsed}
            title={isCollapsed ? "展开侧边栏" : "收起侧边栏"}
            className="flex items-center justify-center w-7 h-7 rounded-lg text-[#7a7a8e] hover:text-[#e8e8ed] hover:bg-white/[0.06] active:scale-95 transition-all cursor-pointer"
          >
            {isCollapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          </button>
        </div>

        {navItems.map((item) => {
          const isActive = currentView === item.id;
          const Icon = item.icon;

          return (
            <button
              key={item.id}
              onClick={() => onViewChange(item.id)}
              title={isCollapsed ? item.label : undefined}
              className={cn(
                "group relative flex items-center h-11 rounded-xl text-left transition-all duration-150 cursor-pointer",
                isCollapsed ? "w-11 justify-center px-0 mx-auto" : "w-full gap-3 px-3.5",
                isActive
                  ? "bg-[#FE2C55]/12 text-[#FE2C55] font-semibold shadow-[0_4px_16px_rgba(254,44,85,0.12)] border border-[#FE2C55]/20"
                  : "text-[#9b9baa] hover:text-[#e8e8ed] hover:bg-white/[0.05]"
              )}
            >
              <Icon className={cn("w-4 h-4 shrink-0 transition-transform group-hover:scale-105", isActive && "text-[#FE2C55]")} />

              {!isCollapsed && (
                <span className="flex-1 text-[0.83rem] truncate">
                  {item.label}
                </span>
              )}

              {item.badge && (
                <span className={cn(
                  "flex items-center justify-center px-1.5 min-w-[18px] h-[18px] rounded-full text-[0.65rem] font-bold bg-[#FE2C55] text-white shadow-[0_2px_8px_rgba(254,44,85,0.4)]",
                  isCollapsed ? "absolute -top-1 -right-1" : "ml-auto"
                )}>
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Bottom Engine Capsule */}
      {!isCollapsed ? (
        <div className="p-3 m-3 rounded-xl bg-white/[0.03] border border-white/[0.06]">
          <div className="flex items-center gap-2 mb-1.5">
            <Zap className="w-3.5 h-3.5 text-[#00d68f]" />
            <span className="text-[0.72rem] font-medium text-[#e8e8ed]">当前转录接口</span>
          </div>
          <div className="text-[0.68rem] text-[#7a7a8e] truncate pl-5">
            {engine}
          </div>
          <div className="mt-2 pt-2 border-t border-white/[0.04] flex items-center justify-between text-[0.65rem] text-[#7a7a8e]">
            <span>版本 v0.2.0</span>
            <span className="text-[#00d68f]">就绪</span>
          </div>
        </div>
      ) : (
        <div className="flex justify-center pb-4 text-[#7a7a8e]">
          <span className="w-2 h-2 rounded-full bg-[#00d68f]" title="已就绪" />
        </div>
      )}
    </aside>
  );
}
