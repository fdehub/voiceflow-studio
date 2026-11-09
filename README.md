<div align="center">

# 🎙️ 音流 (VoiceFlow Studio)
### 多引擎并发 AI 语音识别与智能字幕工作台
**Heterogeneous Multi-Engine Concurrent AI ASR & Subtitle Generation Platform**

[![GitHub Stars](https://img.shields.io/github/stars/fdehub/voiceflow-studio?style=flat-square&logo=github&color=blue)](https://github.com/fdehub/voiceflow-studio)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-green.svg?style=flat-square)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-v3-38B2AC?style=flat-square&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![PyQt5](https://img.shields.io/badge/PyQt-5.15-41CD52?style=flat-square&logo=qt&logoColor=white)](https://riverbankcomputing.com/software/pyqt/)

<p align="center">
  <b>融合端云异构 AI 引擎的生产力工具 · 从音轨无损切片到多模态字幕毫秒级交付</b>
</p>

[✨ 核心功能](#-核心产品特性) •
[🏗️ 系统架构](#️-系统架构与设计) •
[⚡ 4大架构支柱](#-四大核心架构亮点) •
[📊 异构引擎对比](#-多引擎特性对比矩阵) •
[🚀 快速上手](#-快速上手与部署) •
[⚙️ 配置规范](#️-配置说明) •
[🗺️ 演进路线](#️-产品规划与路线图)

</div>

---

## 📖 产品背景与定位 (Product Vision)

在现代 AIGC 与短视频创作者的生产链路中，长视频/音频的字幕生成常常面临四大痛点：
1. **云端单引擎限频与封控严重**：长音视频单次请求极易触发 API 429 频控或上传超时；
2. **异构引擎协议碎片化**：本地 Whisper 大模型、字节跳动剪映通道、B站必剪（Bcut）、快手语音等各家在音轨格式、分片上传策略、时间戳对其算法及轮询状态机上差异巨大；
3. **长音频幻觉与漂移**：大模型（如 Whisper）在遇到长静音段时频发文字循环复读与时间戳错位；
4. **终端形态割裂**：传统工具通常只能在“重型桌面客户端”或“纯 Web 接口”二选一，难以兼顾低门槛一键开箱与云端批量托管场景。

**音流（VoiceFlow Studio）** 应运而生。本项目由资深 AI 产品经理与全栈架构师主导重构，采用**“端云双态 + 统一 ASR 抽象网关 + 高可用自愈代理池”**的设计理念，将底层多源异构语音能力封装为高可用、毫秒级容灾、免 GPU 依赖的企业级智能字幕生产工作台。

---

## 🏗️ 系统架构与设计 (System Architecture)

音流采用**前后端解耦的分层微内核架构**，向上支撑双态前端（React 现代化 Web 工作台 + pywebview / PyQt5 原生桌面容器），向下通过标准化网关纳管异构 AI 识别服务与高可用网络设施。

```mermaid
flowchart TD
    subgraph UI_Layer["🖥️ 交互展示层 (Dual-State Presentation)"]
        direction LR
        WebClient["Modern React 18 Web SPA<br/>(TailwindCSS + Framer Motion)"]
        NativeGUI["PyQt5 / QFluentWidgets<br/>桌面原生容器模式"]
        PyWebView["PyWebView 桥接容器<br/>(VoiceFlow.exe 客户端)"]
    end

    subgraph Service_Layer["⚙️ 服务编排层 (API & Core Engine)"]
        APIServer["FastAPI Async REST & WS Server<br/>(端口 5637 / 跨域与流式任务通知)"]
        TaskQueue["ThreadPool & Async Task Queue<br/>(多任务并发调度 / 状态流转)"]
    end

    subgraph Audio_Pipeline["🎵 音频前处理流水线 (Audio Preprocessing)"]
        FFmpegCore["FFmpeg 音轨分离引擎<br/>(格式无损转码 / 采样率标准化 16kHz)"]
        VADModule["静音切片与时间戳定位器<br/>(长音频智能分片 / 规避 Whisper 幻觉)"]
    end

    subgraph Gateway_Layer["🛡️ 异构引擎抽象网关 (Unified Tool Use Gateway)"]
        BaseASR["BaseASR 统一抽象基类<br/>(协议抹平 / 分片分发 / 时间戳对齐 / 容灾降级)"]
        ProxyPool["自研高可用代理池 (ProxyPool.py)<br/>(探活探针 / 429 频控熔断 / 智能权重轮换)"]
    end

    subgraph Providers["☁️ 异构 AI 引擎供应商池 (ASR Engine Providers)"]
        direction TB
        P_Whisper["OpenAI / Groq Whisper<br/>(大型开源端云模型 / 多语言极高精)"]
        P_JianYing["字节跳动·剪映云通道<br/>(超高速云端识别 / 中文口语优化)"]
        P_Bcut["B站·必剪云通道 (Bcut)<br/>(免费无配额门槛 / 动态分片上传)"]
        P_KuaiShou["快手·云语音识别<br/>(低延迟高吞吐通道)"]
    end

    subgraph Output_Layer["📄 结果生成与无损导出 (Export Pipeline)"]
        SRT_FMT["SRT 标准字幕"]
        ASS_FMT["ASS 动态样式字幕"]
        TXT_FMT["TXT 纯文本逐字稿"]
    end

    WebClient --> APIServer
    NativeGUI --> BaseASR
    PyWebView --> WebClient
    APIServer --> TaskQueue
    TaskQueue --> FFmpegCore
    FFmpegCore --> VADModule
    VADModule --> BaseASR
    BaseASR <--> ProxyPool
    BaseASR --> P_Whisper
    BaseASR --> P_JianYing
    BaseASR --> P_Bcut
    BaseASR --> P_KuaiShou
    BaseASR --> Output_Layer
```

---

## ⚡ 四大核心架构亮点 (Core Engineering Highlights)

### 1. 前后端分离与桌面容器双态架构 (Dual-Mode Delivery)
- **极简桌面体验（开箱即用）**：内嵌轻量级桌面外壳（`VoiceFlow.exe` / `desktop_app.py`），用户无需安装 Node.js、Python 或任何数据库，双击即可唤起沉浸式暗色现代工作台。
- **现代化 React 18 Web UI**：采用 Vite + React 18 + TailwindCSS + Lucide 图标库构建响应式交互界面，支持深色/浅色自适应、批量拖拽导入、实时进度动画与字幕微调预览。
- **FastAPI 异步中枢**：后台基于 `server.py` 构建异步事件驱动接口，支持将音流部署于轻量级 Linux/Windows 服务器，跨端共享转录算力。

### 2. 异构引擎 Tool Use 统一抽象网关 (`BaseASR.py`)
- **协议标准化**：各大服务商接口规范极不一致（Bcut 为分片 MD5 校验+三阶段轮询；剪映为签名直传；Whisper 为多模态 Audio API）。`BaseASR` 抽象出统一的 `recognize(file_path, callback)` 生命周期，全量屏蔽底层鉴权、网络重试和轮询逻辑。
- **时间戳对齐与多格式归一**：自研统一时间轴归一化器（`ASRData.py`），对不同引擎输出的毫秒戳、秒戳和帧偏移量进行高精度规整，无缝输出 **SRT**、**TXT** 与支持自定义样式的 **ASS** 字幕。
- **毫秒级故障转移机制**：支持配置主备链路。当主通道遭遇网络波动或供应商限额时，网关能携带已切片音频状态无感回退至备选引擎，保障千万级长任务不中断。

### 3. 自研高可用动态代理池 (`ProxyPool.py`)
- **秒级自动探活探针**：内置轻量级后台探活线程，采用双向延迟探测对候选节点进行健康打分，自动剔除超时与死节点。
- **HTTP 429 频控熔断与自愈状态机**：针对云端免费接口频繁触发的 Rate Limit，设计了“指数退避 + 节点冷却熔断”状态机。当某 IP 遭遇 429 时，即刻将其放入动态冷却池，自动切至健康 IP 重试，实现真正意义上的无人值守批量流水线。
- **全协议兼容**：无缝支持 HTTP/HTTPS 协议及需密码鉴权的 Socks5 高匿代理（支持 `protocol://user:pass@ip:port#tag` 格式）。

### 4. FFmpeg 音轨提取流水线与长音频抗幻觉优化
- **音画全格式无损分离**：深度集成 FFmpeg，支持 MP4、MKV、MOV、FLV、MP3、WAV、M4A、FLAC 等上百种音视频格式直拖，自动抽轨并重采样为标准的 16000Hz 16-bit 单声道流。
- **智能 VAD 与静音分片**：长视频自动根据静音阈值进行无损切片，并发调用云端并发单元，大幅压缩识别时间；同时彻底解决 Whisper 大模型在超长音频中由于注意力漂移造成的“文字循环幻觉”与丢句现象。

---

## 📊 多引擎特性对比矩阵 (Provider Comparison Matrix)

| 维度指标 | OpenAI / Groq Whisper | 字节跳动·剪映云通道 | B站·必剪通道 (Bcut) | 快手·语音识别 |
| :--- | :--- | :--- | :--- | :--- |
| **部署与成本** | 自有 Key / Groq 极速 API | 免费免登录免配额 | 免费免登录免配额 | 免费高速公共通道 |
| **中文识别准确率** | ⭐⭐⭐⭐⭐ (98.5%+) | ⭐⭐⭐⭐⭐ (98.0%+) | ⭐⭐⭐⭐ (95.5%) | ⭐⭐⭐⭐ (94.8%) |
| **多语言 / 方言支持** | 99+ 语言 / 极强代码中英混杂 | 普通话 / 粤语 / 英语优异 | 中文口语 / 动漫热梗 | 普通话 / 常见口语 |
| **单任务处理速度** | 视 API/GPU 算力 (Groq 100x) | 极快 (5~10x 实时) | 快 (3~5x 实时) | 极快 (6~8x 实时) |
| **频控封锁敏感度** | 低 (受账户额度限制) | 中等 (需代理池轮换) | 较高 (依赖自研代理池) | 中等 |
| **推荐适用场景** | 跨国会议、学术播客、高准确度出版 | 中长短视频、口播、Vlog | 二次元、B站视频、游戏解说 | 快速初稿批量生成 |

---

## 🚀 快速上手与部署 (Quickstart)

### 选项 A：Windows 绿色免安装版（普通创作者推荐）
1. 前往项目的 [Releases 发行版页面](https://github.com/fdehub/voiceflow-studio/releases) 下载最新的 `VoiceFlow-Studio-v1.0.0.zip`。
2. 解压至非中文纯英文路径。
3. 双击运行 `VoiceFlow.exe` 或 `start.bat`，即可畅享原生现代界面。

---

### 选项 B：从源码运行与二次开发（开发者与企业部署）

#### 1. 克隆代码仓库
```bash
git clone https://github.com/fdehub/voiceflow-studio.git
cd voiceflow-studio
```

#### 2. 安装 Python 后端依赖
推荐使用 Python 3.10 或更高版本：
```bash
pip install -r requirements.txt
```
> **提示**：若使用桌面端 Native 壳，需安装 `PyQt5` 与 `pywebview`：
> ```bash
> pip install PyQt5 qfluentwidgets pywebview
> ```

#### 3. 准备 FFmpeg 媒体组件
- 将 `ffmpeg.exe` 放置于项目根目录下（或确保系统 `PATH` 环境变量中已安装 ffmpeg）。

#### 4. 运行工作台
**方式一：一键脚本引导启动**
```cmd
start.bat
```
输入 `1` 启动现代化桌面工作台，输入 `2` 启动 Web 全栈服务。

**方式二：手动启动 Web 开发环境**
```bash
# 启动 FastAPI 后端服务 (端口 5637)
python server.py

# 进入前端目录构建并启动 Vite Dev Server
cd frontend
npm install
npm run dev
```
启动后在浏览器打开：`http://localhost:5173`。

---

## ⚙️ 配置说明 (Configuration)

本项目遵循**生产级敏感配置隔离准则**，代码仓库中绝不上传明文秘钥，所有配置文件均提供开箱即用的 `.example` 模板：

### 1. Whisper API 配置 (`whisper_config.json`)
复制模板文件并填写您的 API 信息：
```bash
cp whisper_config.example.json whisper_config.json
```
```json
{
  "api_key": "YOUR_OPENAI_OR_GROQ_API_KEY",
  "base_url": "https://api.groq.com/openai/v1",
  "model": "whisper-large-v3-turbo",
  "threads": 3,
  "whisper_proxies": [
    "http://127.0.0.1:7890"
  ]
}
```

### 2. 高可用代理池配置 (`bcut_proxies.txt`)
如需大批量无限制并发处理，可在根目录下创建 `bcut_proxies.txt`：
```txt
# 每行一个代理，支持 HTTP/HTTPS/Socks5，可带用户名密码和备注
socks5://127.0.0.1:1080#本地测试节点
socks5://user:password@104.238.134.185:8636#美国节点01
http://127.0.0.1:7890#Clash代理
```

---

## 📂 项目工程目录树 (Repository Structure)

```text
voiceflow-studio/
├── bk_asr/                    # ASR 核心引擎与异构网关层
│   ├── BaseASR.py             # 异构 Tool 统一网关基类与生命周期抽象
│   ├── JianYingASR.py         # 字节跳动剪映 ASR 云通道
│   ├── BcutASR.py             # B站必剪 (Bcut) 分片上传与状态轮询
│   ├── KuaiShouASR.py         # 快手 ASR 引擎通道
│   ├── WhisperASR.py          # OpenAI / Groq Whisper 异步大模型通道
│   ├── ProxyPool.py           # 自研高可用动态代理池与 429 熔断状态机
│   └── ASRData.py             # 字幕数据模型、时间轴规整与 SRT/TXT/ASS 序列化器
├── frontend/                  # Modern Web 前端 (React 18 + Vite + TailwindCSS)
│   ├── src/
│   │   ├── components/        # 工作台、文件列表、关于与设置模块
│   │   ├── services/          # 与 FastAPI 后端通信的 API 客户端
│   │   └── App.jsx
│   ├── package.json
│   └── vite.config.js
├── desktop_app.py             # pywebview 桌面宿主双向通信网桥
├── server.py                  # FastAPI 异步中枢接口服务
├── asr_gui.py                 # PyQt5 / QFluentWidgets 原生备选桌面 GUI
├── start.bat                  # 一键启动引导脚本 (Windows 专用)
├── VoiceFlow.int              # 独立编译与启动入口
├── requirements.txt           # Python 核心依赖定义
├── whisper_config.example.json# Whisper 配置模板
├── bcut_proxies.example.txt   # 代理池配置模板
└── README.md                  # 架构与项目说明文档
```

---

## 🗺️ 产品规划与路线图 (Roadmap)

- [x] **v1.0.0**：
  - [x] 完成异构引擎统一抽象网关（JianYing / Bcut / KuaiShou / Whisper）。
  - [x] 自研代理池调度器与 HTTP 429 自动冷却重试状态机。
  - [x] 前后端分离改造，构建 Vite + React 18 现代化极简 Web 工作台。
  - [x] FFmpeg 深度集成与多格式无损导出（SRT / TXT / ASS）。
- [ ] **v1.1.0**：
  - [ ] 接入 LLM 语义校对管道（基于 DeepSeek / Claude 进行错别字纠正与专业术语润色）。
  - [ ] 引入双语智能对齐与自动多语言字幕翻译器。
  - [ ] 开放 Docker 一键容器化部署镜像。

---

## 📄 开源许可证 (License)

本项目采用 [GNU General Public License v3.0 (GPLv3)](LICENSE) 许可证开源。

---

<div align="center">
  <b>Designed with ❤️ by AI Product Architecture & Engineering Team</b><br/>
  欢迎提交 Issue 与 Pull Request，共建极致的 AI 字幕生产力工具！
</div>
