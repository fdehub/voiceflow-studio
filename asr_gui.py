import concurrent.futures
import json
import logging
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import webbrowser

# 防止在 pythonw 或无控制台模式下因 stdout/stderr 为 None 导致 print 崩溃
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

# 确保当前目录在 sys.path 中，兼容嵌入式 Python runtime
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# FIX: 修复中文路径报错 https://github.com/fdehub/voiceflow-studio/issues/18  设置QT_QPA_PLATFORM_PLUGIN_PATH 
plugin_path = os.path.join(sys.prefix, 'Lib', 'site-packages', 'PyQt5', 'Qt5', 'plugins')
os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugin_path

from PyQt5.QtCore import Qt, QRunnable, QThreadPool, QObject, pyqtSignal as Signal, pyqtSlot as Slot, QSize, QThread, \
    pyqtSignal, QSettings, QRect
from PyQt5.QtGui import QCursor, QColor, QFont, QPainter, QBrush, QPen
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFileDialog,
                             QTableWidgetItem, QHeaderView, QSizePolicy, QFrame,
                             QStyledItemDelegate, QStyle, QStackedWidget, QLabel)
from qfluentwidgets import (ComboBox, PushButton, PrimaryPushButton, LineEdit, PlainTextEdit,
                            TableWidget, FluentIcon as FIF, Action, RoundMenu, InfoBar, InfoBarPosition,
                            FluentWindow, BodyLabel, TitleLabel, SubtitleLabel, CaptionLabel,
                            StrongBodyLabel, MessageBox, CheckBox, CardWidget, SmoothScrollArea,
                            setTheme, setThemeColor, Theme, NavigationItemPosition,
                            SegmentedWidget, SearchLineEdit)

try:
    from .bk_asr.BcutASR import BcutASR
    from .bk_asr.JianYingASR import JianYingASR
    from .bk_asr.WhisperASR import WhisperASR
    from .bk_asr.ASRData import from_subtitle_file
except (ImportError, ValueError):
    from bk_asr.BcutASR import BcutASR
    from bk_asr.JianYingASR import JianYingASR
    from bk_asr.WhisperASR import WhisperASR
    from bk_asr.ASRData import from_subtitle_file

# 设置日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class WorkerSignals(QObject):
    finished = Signal(str, str)
    errno = Signal(str, str)


class ASRWorker(QRunnable):
    """ASR处理工作线程"""
    def __init__(self, file_path, asr_engine, export_format, keep_audio=False):
        super().__init__()
        self.file_path = file_path
        self.asr_engine = asr_engine
        self.export_format = export_format
        self.keep_audio = keep_audio
        self.signals = WorkerSignals()

        self.audio_path = None

    @Slot()
    def run(self):
        temp_audio = None
        is_converted = False
        try:
            save_ext = self.export_format.lower()
            save_path = self.file_path.rsplit(".", 1)[0] + "." + save_ext
            base_no_ext = self.file_path.rsplit(".", 1)[0]

            # 智能极速优化：如果同目录下已存在同名 .srt 或 .ass 字幕，直接转换生成目标格式，0秒完成！
            srt_path = base_no_ext + ".srt"
            ass_path = base_no_ext + ".ass"
            if save_ext == 'txt' and os.path.exists(srt_path):
                logging.info(f"[+] 发现已存在同名字幕 {srt_path}，直接提取文本生成 TXT（0秒极速导出）")
                data = from_subtitle_file(srt_path)
                result_text = data.to_txt()
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(result_text)
                self.signals.finished.emit(self.file_path, result_text)
                return
            elif save_ext == 'ass' and os.path.exists(srt_path):
                logging.info(f"[+] 发现已存在同名字幕 {srt_path}，直接转换为 ASS（0秒极速导出）")
                data = from_subtitle_file(srt_path)
                result_text = data.to_ass()
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(result_text)
                self.signals.finished.emit(self.file_path, result_text)
                return
            elif save_ext == 'srt' and os.path.exists(ass_path):
                logging.info(f"[+] 发现已存在同名字幕 {ass_path}，直接转换为 SRT（0秒极速导出）")
                data = from_subtitle_file(ass_path)
                result_text = data.to_srt()
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(result_text)
                self.signals.finished.emit(self.file_path, result_text)
                return

            use_cache = True
            
            # 检查文件类型,如果不是音频则转换
            logging.info("[+]正在进ffmpeg转换")
            audio_exts = ['.mp3', '.wav']
            if not any(self.file_path.lower().endswith(ext) for ext in audio_exts):
                temp_audio = self.file_path.rsplit(".", 1)[0] + ".mp3"
                if not video2audio(self.file_path, temp_audio):
                    raise Exception("音频转换失败，确保安装ffmpeg")
                self.audio_path = temp_audio
                is_converted = True
            else:
                self.audio_path = self.file_path
            
            # 根据选择的 ASR 引擎实例化相应的类
            if self.asr_engine == 'J 接口':
                asr = JianYingASR(self.audio_path, use_cache=use_cache)
            elif self.asr_engine == 'B 接口':
                asr = BcutASR(self.audio_path, use_cache=use_cache)
            elif self.asr_engine == 'Whisper':
                asr = WhisperASR(self.audio_path, use_cache=use_cache)
            else:
                raise ValueError(f"未知的 ASR 引擎: {self.asr_engine}")

            logging.info(f"开始处理文件: {self.file_path} 使用引擎: {self.asr_engine}")
            result = asr.run()
            
            # 根据导出格式选择转换方法
            save_ext = self.export_format.lower()
            if save_ext == 'srt':
                result_text = result.to_srt()
            elif save_ext == 'ass':
                result_text = result.to_ass()
            elif save_ext == 'txt':
                result_text = result.to_txt()
                
            logging.info(f"完成处理文件: {self.file_path} 使用引擎: {self.asr_engine}")
            save_path = self.file_path.rsplit(".", 1)[0] + "." + save_ext
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(result_text)

            # 如果不保留转换生成的临时音频，则自动清理
            if is_converted and not self.keep_audio and temp_audio and os.path.exists(temp_audio):
                try:
                    os.remove(temp_audio)
                    logging.info(f"已清理临时生成的音频: {temp_audio}")
                except Exception as ex:
                    logging.warning(f"清理临时音频失败: {ex}")

            self.signals.finished.emit(self.file_path, result_text)
        except Exception as e:
            if is_converted and not self.keep_audio and temp_audio and os.path.exists(temp_audio):
                try:
                    os.remove(temp_audio)
                except Exception:
                    pass
            logging.error(f"处理文件 {self.file_path} 时出错: {str(e)}")
            self.signals.errno.emit(self.file_path, f"处理时出错: {str(e)}")

class UpdateCheckerThread(QThread):
    msg = pyqtSignal(str, str, str)  # 用于发送消息的信号

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            from check_update import check_update, check_internet_connection
            # 检查互联网连接
            if not check_internet_connection():
                self.msg.emit("错误", "无法连接到互联网，请检查网络连接。", "")
                return
            # 检查更新
            config = check_update(self)
            if config:
                if config['fource']:
                    self.msg.emit("更新", "检测到新版本，请下载最新版本。", config['update_download_url'])
                else:
                    self.msg.emit("可更新", "检测到新版本，请下载最新版本。", config['update_download_url'])
        except Exception as e:
            pass


class StatusPillDelegate(QStyledItemDelegate):
    """任务状态胶囊 Badge 委托绘制 (对标 D:\\mydouyin 极简设计系统)"""
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # 选中或悬停底色
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(254, 44, 85, 24))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor(255, 255, 255, 8))

        # 底部微细分隔线
        painter.setPen(QPen(QColor(255, 255, 255, 6), 1))
        painter.drawLine(option.rect.left(), option.rect.bottom(), option.rect.right(), option.rect.bottom())

        status = index.data(Qt.DisplayRole) or ""

        # 语义配色规范 (基于 D:\mydouyin index.css: emerald, amber, coral, slate)
        if "已完成" in status or "已处理" in status or status.startswith("✓"):
            bg_color = QColor(0, 214, 143, 26)
            border_color = QColor(0, 214, 143, 75)
            text_color = QColor("#00d68f")
            text = "✓ 已完成"
        elif "失败" in status or "错误" in status or status.startswith("✗"):
            bg_color = QColor(255, 71, 87, 26)
            border_color = QColor(255, 71, 87, 75)
            text_color = QColor("#ff4757")
            text = "✗ 失败"
        elif "处理中" in status:
            bg_color = QColor(250, 140, 22, 26)
            border_color = QColor(250, 140, 22, 75)
            text_color = QColor("#fa8c16")
            text = "⏳ 处理中"
        else:
            bg_color = QColor(255, 255, 255, 12)
            border_color = QColor(255, 255, 255, 25)
            text_color = QColor("#9b9baa")
            text = "等待中"

        pill_height = 24
        pill_width = min(option.rect.width() - 20, 88)
        pill_rect = QRect(
            option.rect.left() + (option.rect.width() - pill_width) // 2,
            option.rect.top() + (option.rect.height() - pill_height) // 2,
            pill_width,
            pill_height
        )

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(pill_rect, 12, 12)

        painter.setPen(text_color)
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pill_rect, Qt.AlignCenter, text)

        painter.restore()


class MediaItemDelegate(QStyledItemDelegate):
    """媒体文件名与路径卡片委托绘制"""
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # 选中或悬停底色
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(254, 44, 85, 24))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor(255, 255, 255, 8))

        # 底部微细分隔线
        painter.setPen(QPen(QColor(255, 255, 255, 6), 1))
        painter.drawLine(option.rect.left(), option.rect.bottom(), option.rect.right(), option.rect.bottom())

        file_path = index.data(Qt.UserRole) or ""
        display_text = index.data(Qt.DisplayRole) or ""
        file_name = os.path.basename(file_path) if file_path else display_text

        ext = os.path.splitext(file_name)[1].lower()
        is_video = ext in ['.mp4', '.mkv', '.avi', '.mov', '.ts', '.flv', '.wmv', '.webm', '.rmvb']

        # 左侧媒体类型微标签: [视] 或 [音]
        badge_rect = QRect(option.rect.left() + 16, option.rect.top() + (option.rect.height() - 22) // 2, 26, 22)
        badge_bg = QColor(254, 44, 85, 25) if is_video else QColor(124, 92, 252, 25)
        badge_border = QColor(254, 44, 85, 75) if is_video else QColor(124, 92, 252, 75)
        badge_text_color = QColor("#FE2C55") if is_video else QColor("#9b7ffc")
        badge_text = "视" if is_video else "音"

        painter.setBrush(QBrush(badge_bg))
        painter.setPen(QPen(badge_border, 1))
        painter.drawRoundedRect(badge_rect, 6, 6)

        painter.setPen(badge_text_color)
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

        # 文件名文本绘制 (自动中间省略)
        text_rect = QRect(
            option.rect.left() + 52,
            option.rect.top(),
            option.rect.width() - 60,
            option.rect.height()
        )
        painter.setPen(QColor("#f0f0f5"))
        font = painter.font()
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)

        elided_text = painter.fontMetrics().elidedText(file_name, Qt.ElideMiddle, text_rect.width() - 8)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided_text)

        painter.restore()


class ASRWidget(QWidget):
    """ASR处理界面 (以 UI 设计师标准重构的 Studio Dark 工作台)"""

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.max_threads = 3  # 设置最大并发线程数
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(self.max_threads)
        self.processing_queue = []
        self.workers = {}  # 维护文件路径到worker的映射

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        # 顶部 Header 标题与全局状态指标胶囊（对标 D:\mydouyin Hero Header）
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(2, 0, 2, 0)
        
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = TitleLabel("转录工作台", self)
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #f2f2f7; letter-spacing: -0.02em;")
        
        version_badge = QLabel("v1.1.0 · 本地极速并发", self)
        version_badge.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                color: #7a7a8e;
                border-radius: 9px;
                padding: 1px 8px;
                font-size: 11px;
                font-weight: 500;
            }
        """)
        title_row.addWidget(title)
        title_row.addWidget(version_badge)
        title_row.addStretch(1)

        subtitle = CaptionLabel("基于多接口并发与本地语音提取的高性能字幕引擎", self)
        subtitle.setStyleSheet("color: #7a7a8e; font-size: 12px; font-weight: 500;")
        title_box.addLayout(title_row)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)

        header_layout.addStretch(1)

        # 右侧全局指标胶囊群（Metrics Capsules）
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(6)
        
        self.badge_total = QLabel("全部 0", self)
        self.badge_waiting = QLabel("待转录 0", self)
        self.badge_running = QLabel("转录中 0", self)
        self.badge_success = QLabel("已完成 0", self)
        self.badge_failed = QLabel("失败 0", self)

        badge_base_qss = "border-radius: 11px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
        self.badge_total.setStyleSheet(f"background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.08); color: #9b9baa; {badge_base_qss}")
        self.badge_waiting.setStyleSheet(f"background: rgba(255, 170, 0, 0.10); border: 1px solid rgba(255, 170, 0, 0.22); color: #ffaa00; {badge_base_qss}")
        self.badge_running.setStyleSheet(f"background: rgba(0, 180, 255, 0.10); border: 1px solid rgba(0, 180, 255, 0.22); color: #00b4ff; {badge_base_qss}")
        self.badge_success.setStyleSheet(f"background: rgba(0, 214, 143, 0.10); border: 1px solid rgba(0, 214, 143, 0.22); color: #00d68f; {badge_base_qss}")
        self.badge_failed.setStyleSheet(f"background: rgba(255, 71, 87, 0.12); border: 1px solid rgba(255, 71, 87, 0.25); color: #ff4757; {badge_base_qss}")
        self.badge_failed.setVisible(False)
        self.badge_running.setVisible(False)

        metrics_layout.addWidget(self.badge_total)
        metrics_layout.addWidget(self.badge_waiting)
        metrics_layout.addWidget(self.badge_running)
        metrics_layout.addWidget(self.badge_success)
        metrics_layout.addWidget(self.badge_failed)

        header_layout.addLayout(metrics_layout)
        layout.addLayout(header_layout)

        # 卡片通用 QSS（精确提取自 D:\mydouyin CSS: #16161e, rgba(255,255,255,0.05)）
        card_qss = """
            QFrame#controlCard, QFrame#queueCard {
                background-color: #16161e;
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
            }
        """

        # 卡片 1: 控制台看板 (Studio Control Deck)
        self.control_card = QFrame(self)
        self.control_card.setObjectName("controlCard")
        self.control_card.setStyleSheet(card_qss)
        control_layout = QVBoxLayout(self.control_card)
        control_layout.setContentsMargins(16, 12, 16, 14)
        control_layout.setSpacing(10)

        # 控制行 1: 核心参数选择 + 强视觉开始按钮 (Primary CTA)
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        lbl_engine = CaptionLabel("接口引擎", self.control_card)
        lbl_engine.setStyleSheet("color: #7a7a8e; font-weight: 600; font-size: 12px;")
        self.combo_box = ComboBox(self.control_card)
        self.combo_box.addItems(['B 接口', 'J 接口', 'Whisper'])
        self.combo_box.setMinimumWidth(110)

        lbl_format = CaptionLabel("导出格式", self.control_card)
        lbl_format.setStyleSheet("color: #7a7a8e; font-weight: 600; font-size: 12px;")
        self.format_combo = ComboBox(self.control_card)
        self.format_combo.addItems(['SRT', 'TXT', 'ASS'])
        self.format_combo.setMinimumWidth(85)

        self.keep_audio_checkbox = CheckBox("保留视频提取的音频 (MP3)", self.control_card)
        self.settings = QSettings("VoiceFlow", "Settings")
        self.keep_audio_checkbox.setChecked(self.settings.value("keep_audio", False, type=bool))
        self.keep_audio_checkbox.stateChanged.connect(
            lambda state: self.settings.setValue("keep_audio", self.keep_audio_checkbox.isChecked())
        )

        row1.addWidget(lbl_engine)
        row1.addWidget(self.combo_box)
        row1.addSpacing(6)
        row1.addWidget(lbl_format)
        row1.addWidget(self.format_combo)
        row1.addSpacing(10)
        row1.addWidget(self.keep_audio_checkbox)
        row1.addStretch(1)

        # 开始批量转录按钮 (保留 38px 左侧 padding 确保图标与文字绝对不重叠)
        self.process_button = PushButton("开始批量转录", self.control_card)
        self.process_button.setIcon(FIF.PLAY)
        self.process_button.setMinimumHeight(35)
        self.process_button.setMinimumWidth(150)
        self.process_button.clicked.connect(self.process_files)
        self.process_button.setEnabled(False)
        self.process_button.setStyleSheet("""
            PushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FE2C55, stop:1 #FF4D73);
                color: #ffffff;
                font-weight: 700;
                font-size: 13px;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 7px;
                padding: 5px 18px 5px 38px;
            }
            PushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF3B62, stop:1 #FF6080);
                border: 1px solid rgba(255, 255, 255, 0.25);
            }
            PushButton:pressed {
                background: #E01E45;
            }
            PushButton:disabled {
                background-color: rgba(255, 255, 255, 0.05);
                color: rgba(255, 255, 255, 0.25);
                border: 1px solid rgba(255, 255, 255, 0.05);
            }
        """)
        row1.addWidget(self.process_button)
        control_layout.addLayout(row1)

        # 控制行 2: 媒体导入 + 批量管理 + 动态失败重试 + 快速搜索
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self.file_button = PushButton("添加媒体", self.control_card)
        self.file_button.setIcon(FIF.ADD)
        self.file_button.clicked.connect(self.select_file)

        self.folder_button = PushButton("导入文件夹", self.control_card)
        self.folder_button.setIcon(FIF.FOLDER)
        self.folder_button.clicked.connect(self.select_folder)

        self.clear_btn = PushButton("清空列表", self.control_card)
        self.clear_btn.setIcon(FIF.DELETE)
        self.clear_btn.clicked.connect(self.clear_all_tasks)

        self.retry_failed_btn = PushButton("重试失败", self.control_card)
        self.retry_failed_btn.setIcon(FIF.SYNC)
        self.retry_failed_btn.setStyleSheet("""
            PushButton {
                background-color: rgba(255, 71, 87, 0.12);
                color: #ff4757;
                border: 1px solid rgba(255, 71, 87, 0.28);
                border-radius: 6px;
                font-weight: 600;
                padding: 5px 14px 6px 36px;
            }
            PushButton:hover {
                background-color: rgba(255, 71, 87, 0.20);
            }
        """)
        self.retry_failed_btn.clicked.connect(self.reprocess_all_failed)
        self.retry_failed_btn.setVisible(False)

        self.export_all_txt_btn = PushButton("快速导出 TXT", self.control_card)
        self.export_all_txt_btn.setIcon(FIF.DOCUMENT)
        self.export_all_txt_btn.clicked.connect(self.export_all_to_txt)
        self.export_all_txt_btn.setToolTip("从列表中已有字幕文件极速提取并生成同名 TXT 文档")

        self.search_input = SearchLineEdit(self.control_card)
        self.search_input.setPlaceholderText("搜索任务列表...")
        self.search_input.setFixedWidth(200)
        self.search_input.textChanged.connect(self.apply_filter)

        row2.addWidget(self.file_button)
        row2.addWidget(self.folder_button)
        row2.addWidget(self.clear_btn)
        row2.addWidget(self.retry_failed_btn)
        row2.addWidget(self.export_all_txt_btn)
        row2.addStretch(1)
        row2.addWidget(self.search_input)
        control_layout.addLayout(row2)

        layout.addWidget(self.control_card)

        # 卡片 2: 任务队列视口 (Task Queue Viewport)
        self.queue_card = QFrame(self)
        self.queue_card.setObjectName("queueCard")
        self.queue_card.setStyleSheet(card_qss)
        queue_layout = QVBoxLayout(self.queue_card)
        queue_layout.setContentsMargins(14, 12, 14, 14)
        queue_layout.setSpacing(10)

        # 视口顶栏：分段筛选器 (Segmented Filter)
        filter_layout = QHBoxLayout()
        queue_title = StrongBodyLabel("任务队列", self.queue_card)
        queue_title.setStyleSheet("color: #e8e8ed; font-size: 13px; font-weight: 700;")
        filter_layout.addWidget(queue_title)
        filter_layout.addSpacing(14)

        self.segmented_filter = SegmentedWidget(self.queue_card)
        self.segmented_filter.addItem('all', '全部')
        self.segmented_filter.addItem('pending', '待处理')
        self.segmented_filter.addItem('completed', '已完成')
        self.segmented_filter.addItem('failed', '失败')
        self.segmented_filter.setCurrentItem('all')
        self.current_status_filter = 'all'
        self.segmented_filter.currentItemChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.segmented_filter)
        filter_layout.addStretch(1)

        queue_layout.addLayout(filter_layout)

        # 视口内容容器：支持 空状态 (Dropzone) 与 任务列表 (Table) 的无缝切换
        self.viewport_stack = QStackedWidget(self.queue_card)

        # Page 0: 空状态拖拽占位区 (Empty Dropzone)
        self.empty_card = QFrame(self.queue_card)
        self.empty_card.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.02);
                border: 2px dashed rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
        """)
        empty_layout = QVBoxLayout(self.empty_card)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(12)

        drop_title = StrongBodyLabel("拖拽媒体文件或文件夹至此处", self.empty_card)
        drop_title.setStyleSheet("color: #e8e8ed; font-size: 15px; font-weight: 600; border: none; background: transparent;")
        drop_hint = CaptionLabel("支持 MP4 · MOV · MKV · TS · MP3 · WAV · M4A · FLAC 等常见音视频格式", self.empty_card)
        drop_hint.setStyleSheet("color: #7a7a8e; font-size: 12px; border: none; background: transparent;")

        empty_btn_box = QHBoxLayout()
        empty_btn_box.setSpacing(12)
        btn_browse_file = PushButton("选取媒体文件", self.empty_card)
        btn_browse_file.setIcon(FIF.ADD)
        btn_browse_file.clicked.connect(self.select_file)
        btn_browse_folder = PushButton("导入整个文件夹", self.empty_card)
        btn_browse_folder.setIcon(FIF.FOLDER)
        btn_browse_folder.clicked.connect(self.select_folder)
        empty_btn_box.addWidget(btn_browse_file)
        empty_btn_box.addWidget(btn_browse_folder)

        empty_layout.addStretch(1)
        empty_layout.addWidget(drop_title, alignment=Qt.AlignCenter)
        empty_layout.addWidget(drop_hint, alignment=Qt.AlignCenter)
        empty_layout.addSpacing(6)
        empty_layout.addLayout(empty_btn_box)
        empty_layout.addStretch(1)

        self.viewport_stack.addWidget(self.empty_card)

        # Page 1: 媒体任务列表表格 (完全消除多余白边与原生边框)
        self.table = TableWidget(self.queue_card)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(['媒体任务 (文件名 / 路径)', '转录状态'])
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.itemDoubleClicked.connect(self.on_table_item_double_clicked)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        
        # 彻底隐藏纵向序号列与左上角原生白色方块，完全禁用内部框架白边
        self.table.verticalHeader().hide()
        self.table.setCornerButtonEnabled(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setFrameShadow(QFrame.Plain)
        self.table.setLineWidth(0)
        self.table.setBorderVisible(False)

        # 安装自定义高保真绘制代理 (MediaItemDelegate & StatusPillDelegate)
        self.table.setItemDelegateForColumn(0, MediaItemDelegate(self.table))
        self.table.setItemDelegateForColumn(1, StatusPillDelegate(self.table))

        self.table.setStyleSheet("""
            QTableView, QTableWidget {
                background-color: transparent;
                border: none;
                gridline-color: transparent;
                color: #e8e8ed;
                selection-background-color: rgba(254, 44, 85, 0.16);
                outline: none;
            }
            QTableView::item {
                background-color: transparent;
                border: none;
            }
            QHeaderView {
                background-color: transparent;
                border: none;
            }
            QHeaderView::section {
                background-color: transparent;
                color: #7a7a8e;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                padding: 6px 16px;
                font-weight: 600;
                font-size: 12px;
            }
            QTableCornerButton::section {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.12);
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.25);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 130)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.viewport_stack.addWidget(self.table)
        queue_layout.addWidget(self.viewport_stack)

        layout.addWidget(self.queue_card, stretch=1)

        self.setAcceptDrops(True)
        self.load_task_history()
        self.update_stats()
        self.update_start_button_state()

    def update_stats(self):
        """刷新任务队列各项状态计数与空状态切换"""
        total = self.table.rowCount()
        waiting = 0
        processing = 0
        completed = 0
        failed = 0
        for row in range(total):
            item = self.table.item(row, 1)
            if not item:
                continue
            text = item.text()
            if "处理中" in text:
                processing += 1
            elif "已完成" in text or "已处理" in text or text.startswith("✓"):
                completed += 1
            elif "失败" in text or "错误" in text or text.startswith("✗"):
                failed += 1
            else:
                waiting += 1

        self.badge_total.setText(f"全部 {total}")
        self.badge_waiting.setText(f"待转录 {waiting}")
        self.badge_running.setText(f"转录中 {processing}")
        self.badge_success.setText(f"已完成 {completed}")
        self.badge_failed.setText(f"失败 {failed}")

        self.badge_failed.setVisible(failed > 0)
        self.badge_running.setVisible(processing > 0)

        # 空状态智能切换
        if hasattr(self, 'viewport_stack'):
            self.viewport_stack.setCurrentIndex(1 if total > 0 else 0)

        self.apply_filter()

    def select_file(self):
        """选择文件对话框"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择音频或视频文件", "",
            "Media Files (*.mp3 *.wav *.ogg *.flac *.aac *.m4a *.mp4 *.avi *.mov *.ts *.mkv *.wmv *.flv *.webm)"
        )
        for file in files:
            self.add_file_to_table(file)
        self.update_start_button_state()
        self.update_stats()

    def select_folder(self):
        """选择文件夹并递归导入其中的媒体文件"""
        folder = QFileDialog.getExistingDirectory(self, "选择包含媒体文件的文件夹", "")
        if not folder:
            return
        supported_formats = ('.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma',
                             '.mp4', '.avi', '.mov', '.ts', '.mkv', '.wmv', '.flv', '.webm', '.rmvb')
        added_count = 0
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(supported_formats):
                    self.add_file_to_table(os.path.join(root, f))
                    added_count += 1
        self.update_start_button_state()
        self.update_stats()
        if added_count > 0:
            InfoBar.success(
                title='导入完成',
                content=f"已从文件夹导入 {added_count} 个媒体文件",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2500,
                parent=self.window()
            )

    def add_file_to_table(self, file_path, initial_status="未处理"):
        """将文件添加到表格中"""
        if self.find_row_by_file_path(file_path) != -1:
            InfoBar.warning(
                title='文件已存在',
                content=f"文件 {os.path.basename(file_path)} 已经添加到列表中。",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self.window()
            )
            return

        row_count = self.table.rowCount()
        self.table.insertRow(row_count)
        self.table.setRowHeight(row_count, 44)
        item_filename = self.create_non_editable_item(os.path.basename(file_path))
        item_filename.setData(Qt.UserRole, file_path)
        item_filename.setToolTip(file_path)
        
        display_status = initial_status
        # 检测磁盘上是否已有导出的字幕或文本（SRT/TXT/ASS）
        base_no_ext = file_path.rsplit(".", 1)[0]
        has_sub_file = (
            os.path.exists(base_no_ext + ".srt") or
            os.path.exists(base_no_ext + ".txt") or
            os.path.exists(base_no_ext + ".ass")
        )

        if "已完成" in initial_status or "已处理" in initial_status or initial_status.startswith("✓") or has_sub_file:
            display_status = "✓ 已完成"
        elif "失败" in initial_status or "错误" in initial_status or initial_status.startswith("✗"):
            display_status = "✗ 失败"
        elif "处理中" in initial_status:
            display_status = "⏳ 处理中..."
        else:
            display_status = "等待中"

        item_status = self.create_non_editable_item(display_status)
        self.table.setItem(row_count, 0, item_filename)
        self.table.setItem(row_count, 1, item_status)

        self.save_task_history()
        self.update_stats()
        self.update_start_button_state()

    def create_non_editable_item(self, text):
        """创建不可编辑的表格项"""
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def on_table_item_double_clicked(self, item):
        """双击表格行直接在系统文件资源管理器中定位文件"""
        row = item.row()
        file_item = self.table.item(row, 0)
        if not file_item:
            return
        file_path = file_item.data(Qt.UserRole)
        if not file_path or not os.path.exists(file_path):
            return
        try:
            if platform.system() == "Windows":
                subprocess.Popen(f'explorer /select,"{os.path.abspath(file_path)}"')
            else:
                os.startfile(os.path.dirname(file_path))
        except Exception:
            pass

    def on_filter_changed(self, key):
        """分段切换过滤器触发"""
        self.current_status_filter = key
        self.apply_filter()

    def apply_filter(self):
        """根据当前筛选分段和搜索关键词过滤表格显示"""
        if not hasattr(self, 'search_input') or not hasattr(self, 'table'):
            return
        search_text = self.search_input.text().strip().lower()
        filter_type = getattr(self, 'current_status_filter', 'all')

        for row in range(self.table.rowCount()):
            item_file = self.table.item(row, 0)
            item_status = self.table.item(row, 1)
            if not item_file or not item_status:
                continue

            file_path = (item_file.data(Qt.UserRole) or "").lower()
            file_name = (item_file.text() or "").lower()
            status_text = item_status.text()

            match_search = not search_text or (search_text in file_name or search_text in file_path)

            match_status = True
            if filter_type == "pending":
                match_status = "已完成" not in status_text and "已处理" not in status_text and "处理中" not in status_text and "失败" not in status_text and not status_text.startswith("✓") and not status_text.startswith("✗")
            elif filter_type == "completed":
                match_status = "已完成" in status_text or "已处理" in status_text or status_text.startswith("✓")
            elif filter_type == "failed":
                match_status = "失败" in status_text or "错误" in status_text or status_text.startswith("✗")

            self.table.setRowHidden(row, not (match_search and match_status))

    def show_context_menu(self, pos):
        """显示右键菜单"""
        current_row = self.table.rowAt(pos.y())
        if current_row < 0:
            return

        self.table.selectRow(current_row)

        menu = RoundMenu(parent=self)
        export_txt_action = Action(FIF.DOCUMENT, "从同名字幕快速导出 TXT (0秒)")
        reprocess_action = Action(FIF.SYNC, "重新处理此文件")
        retry_all_action = Action(FIF.UPDATE, "重试所有失败任务")
        open_dir_action = Action(FIF.FOLDER, "打开文件所在目录")
        delete_action = Action(FIF.DELETE, "删除任务")
        clear_action = Action(FIF.CLOSE, "清空列表")
        menu.addActions([export_txt_action, reprocess_action, retry_all_action, open_dir_action, delete_action, clear_action])

        export_txt_action.triggered.connect(self.export_subtitle_to_txt)
        delete_action.triggered.connect(self.delete_selected_row)
        open_dir_action.triggered.connect(self.open_file_directory)
        reprocess_action.triggered.connect(self.reprocess_selected_file)
        retry_all_action.triggered.connect(self.reprocess_all_failed)
        clear_action.triggered.connect(self.clear_all_tasks)

        menu.exec(QCursor.pos())

    def export_subtitle_to_txt(self):
        """如果同目录下已有字幕，直接提取文本生成 TXT，0.1秒完成"""
        current_row = self.table.currentRow()
        if current_row >= 0:
            item = self.table.item(current_row, 0)
            if not item:
                return
            file_path = item.data(Qt.UserRole)
            base_no_ext = file_path.rsplit(".", 1)[0]
            srt_path = base_no_ext + ".srt"
            ass_path = base_no_ext + ".ass"
            txt_path = base_no_ext + ".txt"

            sub_path = srt_path if os.path.exists(srt_path) else (ass_path if os.path.exists(ass_path) else None)
            if not sub_path:
                InfoBar.warning(
                    title='未找到字幕',
                    content=f"未找到对应的字幕文件：{os.path.basename(srt_path)}",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2500,
                    parent=self.window()
                )
                return

            try:
                data = from_subtitle_file(sub_path)
                result_text = data.to_txt()
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(result_text)
                InfoBar.success(
                    title='导出成功',
                    content=f"已成功秒级导出：{os.path.basename(txt_path)}",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2500,
                    parent=self.window()
                )
            except Exception as e:
                InfoBar.error(
                    title='导出失败',
                    content=str(e),
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self.window()
                )

    def export_all_to_txt(self):
        """一键批量将列表中所有已有字幕的任务极速转换为 TXT 纯文本"""
        total = self.table.rowCount()
        success_count = 0
        for row in range(total):
            item = self.table.item(row, 0)
            if not item:
                continue
            file_path = item.data(Qt.UserRole)
            if not file_path:
                continue
            base_no_ext = file_path.rsplit(".", 1)[0]
            srt_path = base_no_ext + ".srt"
            ass_path = base_no_ext + ".ass"
            txt_path = base_no_ext + ".txt"

            sub_path = srt_path if os.path.exists(srt_path) else (ass_path if os.path.exists(ass_path) else None)
            if not sub_path:
                continue
            try:
                data = from_subtitle_file(sub_path)
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(data.to_txt())
                success_count += 1
            except Exception:
                pass

        if success_count > 0:
            InfoBar.success(
                title="TXT 导出成功",
                content=f"已秒级快速导出 {success_count} 个任务的同名 TXT 文本文档！",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self.window()
            )
        else:
            InfoBar.warning(
                title="未找到可用字幕",
                content="当前列表中尚未找到已完成的 .srt 或 .ass 字幕文件。",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self.window()
            )

    def save_task_history(self):
        """保存任务列表历史到配置中"""
        try:
            tasks = []
            for row in range(self.table.rowCount()):
                item_file = self.table.item(row, 0)
                item_status = self.table.item(row, 1)
                if item_file and item_status:
                    tasks.append({
                        "path": item_file.data(Qt.UserRole),
                        "status": item_status.text()
                    })
            self.settings.setValue("task_history", json.dumps(tasks, ensure_ascii=False))
        except Exception as e:
            logging.warning(f"保存任务历史失败: {e}")

    def load_task_history(self):
        """从配置中恢复任务列表"""
        raw = self.settings.value("task_history", "[]", type=str)
        try:
            tasks = json.loads(raw)
            for t in tasks:
                path = t.get("path")
                status = t.get("status", "未处理")
                if path and os.path.exists(path):
                    self.add_file_to_table(path, initial_status=status)
        except Exception as e:
            logging.warning(f"恢复任务历史失败: {e}")

    def clear_all_tasks(self):
        """清空表格任务"""
        self.table.setRowCount(0)
        self.processing_queue.clear()
        self.save_task_history()
        self.update_start_button_state()
        self.update_stats()

    def reprocess_all_failed(self):
        """重试所有失败的文件"""
        for row in range(self.table.rowCount()):
            status = self.table.item(row, 1).text()
            if "失败" in status or "错误" in status or status.startswith("✗"):
                file_path = self.table.item(row, 0).data(Qt.UserRole)
                if file_path not in self.processing_queue and file_path not in self.workers:
                    self.processing_queue.append(file_path)
        self.process_next_in_queue()
        self.update_stats()

    def delete_selected_row(self):
        """删除选中的行"""
        current_row = self.table.currentRow()
        if current_row >= 0:
            file_path = self.table.item(current_row, 0).data(Qt.UserRole)
            if file_path in self.workers:
                worker = self.workers[file_path]
                worker.signals.finished.disconnect(self.update_table)
                worker.signals.errno.disconnect(self.handle_error)
                self.workers.pop(file_path, None)
            self.table.removeRow(current_row)
            self.save_task_history()
            self.update_start_button_state()
            self.update_stats()

    def open_file_directory(self):
        """打开文件所在目录"""
        current_row = self.table.currentRow()
        if current_row >= 0:
            current_item = self.table.item(current_row, 0)
            if current_item:
                file_path = current_item.data(Qt.UserRole)
                directory = os.path.dirname(file_path)
                try:
                    if platform.system() == "Windows":
                        os.startfile(directory)
                    elif platform.system() == "Darwin":
                        subprocess.Popen(["open", directory])
                    else:
                        subprocess.Popen(["xdg-open", directory])
                except Exception as e:
                    InfoBar.error(
                        title='无法打开目录',
                        content=str(e),
                        orient=Qt.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=3000,
                        parent=self.window()
                    )

    def reprocess_selected_file(self):
        """重新处理选中的文件"""
        current_row = self.table.currentRow()
        if current_row >= 0:
            file_path = self.table.item(current_row, 0).data(Qt.UserRole)
            status = self.table.item(current_row, 1).text()
            if "处理中" in status:
                InfoBar.warning(
                    title='当前文件正在处理中',
                    content="请等待当前文件处理完成后再重新处理。",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self.window()
                )
                return
            self.add_to_queue(file_path)

    def add_to_queue(self, file_path):
        """将文件添加到处理队列并更新状态"""
        self.processing_queue.append(file_path)
        self.process_next_in_queue()

    def process_files(self):
        """处理所有待转录或出错重试的文件"""
        for row in range(self.table.rowCount()):
            status = self.table.item(row, 1).text()
            if ("等待中" in status or "未处理" in status or "失败" in status or "错误" in status or status.startswith("✗")) and "处理中" not in status:
                file_path = self.table.item(row, 0).data(Qt.UserRole)
                if file_path not in self.processing_queue and file_path not in self.workers:
                    self.processing_queue.append(file_path)
        self.process_next_in_queue()

    def process_next_in_queue(self):
        """处理队列中的下一个文件"""
        while self.thread_pool.activeThreadCount() < self.max_threads and self.processing_queue:
            file_path = self.processing_queue.pop(0)
            if file_path not in self.workers:
                self.process_file(file_path)

    def process_file(self, file_path):
        """处理单个文件"""
        selected_engine = self.combo_box.currentText()
        selected_format = self.format_combo.currentText()
        keep_audio = self.keep_audio_checkbox.isChecked()
        worker = ASRWorker(file_path, selected_engine, selected_format, keep_audio=keep_audio)
        worker.signals.finished.connect(self.update_table)
        worker.signals.errno.connect(self.handle_error)
        self.thread_pool.start(worker)
        self.workers[file_path] = worker

        row = self.find_row_by_file_path(file_path)
        if row != -1:
            status_item = self.create_non_editable_item("⏳ 处理中...")
            self.table.setItem(row, 1, status_item)
            self.update_start_button_state()
            self.update_stats()

    def update_table(self, file_path, result):
        """更新表格中文件的处理状态"""
        row = self.find_row_by_file_path(file_path)
        if row != -1:
            item_status = self.create_non_editable_item("✓ 已完成")
            self.table.setItem(row, 1, item_status)

            InfoBar.success(
                title='处理完成',
                content=f"文件 {self.table.item(row, 0).text()} 已完成识别与字幕导出",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=1800,
                parent=self.window()
            )

        self.workers.pop(file_path, None)
        self.save_task_history()
        self.process_next_in_queue()
        self.update_start_button_state()
        self.update_stats()

    def handle_error(self, file_path, error_message):
        """处理错误信息"""
        row = self.find_row_by_file_path(file_path)
        if row != -1:
            item_status = self.create_non_editable_item("✗ 失败")
            self.table.setItem(row, 1, item_status)

            InfoBar.error(
                title='处理出错',
                content=error_message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self.window()
            )

        self.workers.pop(file_path, None)
        self.save_task_history()
        self.process_next_in_queue()
        self.update_start_button_state()
        self.update_stats()

    def find_row_by_file_path(self, file_path):
        """根据文件路径查找表格中的行号"""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == file_path:
                return row
        return -1

    def update_start_button_state(self):
        """根据待处理任务数量动态更新开始批量转录与失败重试按钮"""
        runnable_count = 0
        failed_count = 0
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if not item:
                runnable_count += 1
                continue
            text = item.text()
            if "失败" in text or "错误" in text or text.startswith("✗"):
                failed_count += 1
                runnable_count += 1
            elif "已完成" not in text and "已处理" not in text and "处理中" not in text and not text.startswith("✓"):
                runnable_count += 1

        if runnable_count > 0:
            self.process_button.setEnabled(True)
            self.process_button.setText(f"开始批量转录 ({runnable_count})")
        else:
            self.process_button.setEnabled(False)
            self.process_button.setText("开始批量转录")

        if hasattr(self, 'retry_failed_btn'):
            if failed_count > 0:
                self.retry_failed_btn.setVisible(True)
                self.retry_failed_btn.setText(f"重试失败 ({failed_count})")
            else:
                self.retry_failed_btn.setVisible(False)

    def dragEnterEvent(self, event):
        """拖拽进入事件"""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """拖拽释放事件"""
        supported_formats = ('.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma',
                             '.mp4', '.avi', '.mov', '.ts', '.mkv', '.wmv', '.flv', '.webm', '.rmvb')
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for file in files:
            if os.path.isdir(file):
                for root, dirs, files_in_dir in os.walk(file):
                    for f in files_in_dir:
                        if f.lower().endswith(supported_formats):
                            self.add_file_to_table(os.path.join(root, f))
            elif file.lower().endswith(supported_formats):
                self.add_file_to_table(file)
        self.update_start_button_state()


class InfoWidget(QWidget):
    """个人信息界面"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        GITHUB_URL = "https://github.com/fdehub/voiceflow-studio"

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignTop)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        title = TitleLabel("关于 音流 (VoiceFlow Studio)", self)
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #f2f2f7;")
        subtitle = CaptionLabel("多引擎并发 AI 语音识别与智能字幕工作台", self)
        subtitle.setStyleSheet("color: #8e8e9d; font-size: 13px;")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        main_layout.addLayout(header_layout)

        card = CardWidget(self)
        card.setStyleSheet("""
            CardWidget {
                background-color: #16161e;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(16)

        brand_title = StrongBodyLabel("⚡ VoiceFlow Studio v1.0.0", card)
        brand_title.setStyleSheet("font-size: 18px; color: #FE2C55; font-weight: bold;")
        card_layout.addWidget(brand_title)

        features = [
            ("🚀 无需复杂配置", "无需 GPU 和繁琐的本地 Python/CUDA 环境配置，开箱即用。"),
            ("🖥️ 极客暗黑界面", "借鉴现代桌面极简设计，结合 QFluentWidgets 流畅控件与暗黑主题。"),
            ("⚡ 效率并发架构", "多线程任务并发队列 + 秒级字幕文本提取，转录处理快如闪电。"),
            ("🛡️ 智能代理池", "内置多节点轮询测速代理池与自动冷却机制，稳定突破服务限频。"),
            ("📄 多格式导出", "原生支持导出 SRT、ASS、TXT 等主流字幕与纯文本文档。")
        ]

        for feat_title, feat_desc in features:
            f_box = QVBoxLayout()
            f_box.setSpacing(2)
            t_lbl = StrongBodyLabel(feat_title, card)
            t_lbl.setStyleSheet("color: #e8e8ed; font-size: 14px;")
            d_lbl = CaptionLabel(feat_desc, card)
            d_lbl.setStyleSheet("color: #8e8e9d; font-size: 12px;")
            f_box.addWidget(t_lbl)
            f_box.addWidget(d_lbl)
            card_layout.addLayout(f_box)

        card_layout.addSpacing(8)

        btn_box = QHBoxLayout()
        github_button = PrimaryPushButton("访问 GitHub 开源仓库", card)
        github_button.setIcon(FIF.GITHUB)
        github_button.setIconSize(QSize(18, 18))
        github_button.setMinimumHeight(38)
        github_button.clicked.connect(lambda _: webbrowser.open(GITHUB_URL))
        btn_box.addWidget(github_button)
        btn_box.addStretch(1)
        card_layout.addLayout(btn_box)

        main_layout.addWidget(card)



class TestThread(QThread):
    finished_signal = Signal(bool, str)

    def __init__(self, base_url, api_key, model, proxy=None):
        super().__init__()
        self.base_url = (base_url or "").strip().rstrip('/')
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.proxy = (proxy or "").strip() if proxy else None

    def run(self):
        try:
            import requests
            proxies = None
            if self.proxy:
                p = self.proxy.strip()
                if p.lower().startswith("socks5://"):
                    p = "socks5h://" + p[len("socks5://"):]
                proxies = {"http": p, "https": p}

            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            # 探测 models 接口连通性
            test_url = f"{self.base_url}/models"
            resp = requests.get(test_url, headers=headers, proxies=proxies, timeout=12)
            if resp.status_code == 200:
                self.finished_signal.emit(True, f"接口连接成功！(HTTP 200 OK)\n网络与代理连通正常，服务端已正确响应。")
            elif resp.status_code == 401:
                self.finished_signal.emit(False, f"已连接到服务端，但认证失败 (HTTP 401)\n请检查 API Key 是否有效。")
            elif resp.status_code == 403:
                self.finished_signal.emit(False, f"访问受限 (HTTP 403)\n提示：服务提供商限制了此 IP 或账户访问。")
            elif resp.status_code == 400 and "restricted" in resp.text.lower():
                self.finished_signal.emit(False, f"网络连接与代理畅通，但账号受限 (HTTP 400)\n{resp.text[:120]}")
            else:
                self.finished_signal.emit(False, f"服务端响应状态异常: HTTP {resp.status_code}\n{resp.text[:150]}")
        except Exception as e:
            self.finished_signal.emit(False, f"网络请求失败: {str(e)}")


class BcutProxyTestThread(QThread):
    progress_signal = Signal(int, int, str)
    finished_signal = Signal(int, int, str, list)

    def __init__(self, proxies):
        super().__init__()
        self.proxies = proxies

    def run(self):
        try:
            from bk_asr.ProxyPool import BcutProxyPool
            total = len(self.proxies)
            if total == 0:
                self.finished_signal.emit(0, 0, "没有待测试的代理节点", [])
                return

            results = [None] * total
            completed = 0
            lock = threading.Lock()

            def test_one(idx, proxy_item):
                nonlocal completed
                ok, msg = BcutProxyPool.test_single_proxy(proxy_item, timeout=6)
                with lock:
                    completed += 1
                    results[idx] = (ok, proxy_item, msg)
                    self.progress_signal.emit(completed, total, msg)

            # 多线程高并发同时探测所有节点（最多 10 线程并发）
            max_workers = min(total, 10)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(test_one, i, p) for i, p in enumerate(self.proxies)]
                concurrent.futures.wait(futures)

            success = sum(1 for r in results if r and r[0])
            fail = total - success
            details = []
            for r in results:
                if not r:
                    continue
                ok, p, msg = r
                symbol = "✓" if ok else "✗"
                details.append(f"{symbol} {msg}")

            summary = f"测试完成: {success} 个可用, {fail} 个失败\n" + "\n".join(details[:8])
            if len(details) > 8:
                summary += f"\n... 等共 {len(details)} 个节点"
            self.finished_signal.emit(success, fail, summary, results)
        except Exception as e:
            self.finished_signal.emit(0, len(self.proxies), f"测试异常: {str(e)}", [])


class ConfigWidget(SmoothScrollArea):
    """接口配置与管理界面"""

    PRESETS = {
        "SiliconFlow 硅基流动 (国内直连/推荐)": {
            "base_url": "https://api.siliconflow.cn/v1",
            "model": "FunAudioLLM/SenseVoiceSmall",
            "hint": "国内直连无需代理，新用户注册赠送额度，支持 SenseVoice 与 Whisper 等模型"
        },
        "Groq 极速转录 (免费高并发/需海外代理)": {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "whisper-large-v3-turbo",
            "hint": "海外服务响应速度极快，免费支持多 Key 轮换，需在网络代理一栏填写 HTTP 或 SOCKS5 代理"
        },
        "OpenAI 官方服务 (需海外代理)": {
            "base_url": "https://api.openai.com/v1",
            "model": "whisper-1",
            "hint": "OpenAI 官方 Whisper 接口，按转录时长计费，国内访问需配置代理"
        },
        "本地 FastWhisper / LocalAI 服务": {
            "base_url": "http://localhost:8000/v1",
            "model": "whisper-1",
            "hint": "本地部署的 OpenAI 兼容语音识别服务，完全离线与私密"
        },
        "自定义兼容服务 (Custom)": {
            "base_url": "",
            "model": "",
            "hint": "支持任意遵循 OpenAI 规范 (/audio/transcriptions) 的语音大模型服务"
        }
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setObjectName("configWidget")
        self.test_thread = None
        self.init_ui()
        self.load_config()

    def init_ui(self):
        self.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
        """)
        container = QWidget(self)
        container.setObjectName("configContainer")
        container.setStyleSheet("""
            QWidget#configContainer {
                background-color: transparent;
            }
        """)
        self.setWidget(container)

        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(32, 24, 32, 28)
        main_layout.setSpacing(18)
        main_layout.setAlignment(Qt.AlignTop)

        # 标题栏
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        title_label = TitleLabel("接口配置与管理", container)
        title_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #f2f2f7;")
        subtitle_label = CaptionLabel(
            "在此配置第三方 Whisper 兼容大模型接口（支持多 Key 自动负载均衡、HTTP / SOCKS5 代理与一键连通性测试）。",
            container
        )
        subtitle_label.setStyleSheet("color: #8e8e9d; font-size: 13px;")
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        main_layout.addLayout(header_layout)

        card_style = """
            CardWidget {
                background-color: #16161e;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
        """

        # 卡片容器 1: Whisper 兼容接口
        card = CardWidget(container)
        card.setStyleSheet(card_style)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 24)
        card_layout.setSpacing(16)

        # 快速预设
        preset_layout = QVBoxLayout()
        preset_layout.setSpacing(6)
        preset_label = StrongBodyLabel("服务商快速预设", card)
        preset_label.setStyleSheet("color: #e8e8ed; font-size: 14px;")
        self.preset_combo = ComboBox(card)
        for name in self.PRESETS.keys():
            self.preset_combo.addItem(name)
        self.preset_hint = CaptionLabel("", card)
        self.preset_hint.setStyleSheet("color: #FE2C55; font-size: 12px;")
        preset_layout.addWidget(preset_label)
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addWidget(self.preset_hint)
        card_layout.addLayout(preset_layout)

        # 接口 Base URL
        url_layout = QVBoxLayout()
        url_layout.setSpacing(6)
        url_label = BodyLabel("接口地址 (Base URL):", card)
        url_label.setStyleSheet("color: #9b9baa;")
        self.url_edit = LineEdit(card)
        self.url_edit.setPlaceholderText("例如: https://api.siliconflow.cn/v1")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_edit)
        card_layout.addLayout(url_layout)

        # 模型名称
        model_layout = QVBoxLayout()
        model_layout.setSpacing(6)
        model_label = BodyLabel("模型名称 (Model):", card)
        model_label.setStyleSheet("color: #9b9baa;")
        self.model_edit = LineEdit(card)
        self.model_edit.setPlaceholderText("例如: FunAudioLLM/SenseVoiceSmall 或 whisper-large-v3-turbo")
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_edit)
        card_layout.addLayout(model_layout)

        # 网络代理
        proxy_layout = QVBoxLayout()
        proxy_layout.setSpacing(6)
        proxy_label = BodyLabel("网络代理 (Proxy，支持 HTTP 与 SOCKS5):", card)
        proxy_label.setStyleSheet("color: #9b9baa;")
        self.proxy_edit = LineEdit(card)
        self.proxy_edit.setPlaceholderText("例如 socks5://Misaka:Misaka@140.238.42.26:8636 或 http://127.0.0.1:10808 (国内服务留空)")
        proxy_layout.addWidget(proxy_label)
        proxy_layout.addWidget(self.proxy_edit)
        card_layout.addLayout(proxy_layout)

        # API Key 列表
        key_layout = QVBoxLayout()
        key_layout.setSpacing(6)
        key_title_layout = QHBoxLayout()
        key_label = BodyLabel("API 密钥列表 (一行一个 Key，支持多 Key 负载均衡轮换):", card)
        key_label.setStyleSheet("color: #9b9baa;")
        key_title_layout.addWidget(key_label)
        key_title_layout.addStretch(1)
        self.key_count_label = CaptionLabel("当前已配置: 0 个", card)
        self.key_count_label.setStyleSheet("color: #7a7a8e; font-size: 12px;")
        key_title_layout.addWidget(self.key_count_label)

        self.key_edit = PlainTextEdit(card)
        self.key_edit.setPlaceholderText("在此粘贴您的 API Key，支持多行输入。\n每发起一次音频转录请求，程序会自动轮询切换下一个 Key，突破速率限制。")
        self.key_edit.setMinimumHeight(130)
        self.key_edit.textChanged.connect(self.update_key_count)
        key_layout.addLayout(key_title_layout)
        key_layout.addWidget(self.key_edit)
        card_layout.addLayout(key_layout)

        # 操作按钮栏
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.test_btn = PushButton("测试当前接口连接", card)
        self.test_btn.setIcon(FIF.SYNC)
        self.test_btn.setMinimumHeight(38)
        self.test_btn.clicked.connect(self.on_test_connection)

        self.save_btn = PrimaryPushButton("保存配置", card)
        self.save_btn.setIcon(FIF.SAVE)
        self.save_btn.setMinimumHeight(38)
        self.save_btn.clicked.connect(self.save_config)

        btn_layout.addWidget(self.test_btn)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.save_btn)
        card_layout.addLayout(btn_layout)

        main_layout.addWidget(card)

        # 卡片容器 2: B 接口专属代理池
        bcut_card = CardWidget(container)
        bcut_card.setStyleSheet(card_style)
        bcut_layout = QVBoxLayout(bcut_card)
        bcut_layout.setContentsMargins(24, 20, 24, 24)
        bcut_layout.setSpacing(16)

        bcut_title_layout = QHBoxLayout()
        bcut_card_title = StrongBodyLabel("B 接口 (必剪) 专属代理池", bcut_card)
        bcut_card_title.setStyleSheet("color: #e8e8ed; font-size: 14px; font-weight: bold;")
        bcut_title_layout.addWidget(bcut_card_title)
        bcut_title_layout.addStretch(1)
        self.bcut_count_label = CaptionLabel("当前已配置: 0 个代理", bcut_card)
        self.bcut_count_label.setStyleSheet("color: #7a7a8e; font-size: 12px;")
        bcut_title_layout.addWidget(self.bcut_count_label)
        bcut_layout.addLayout(bcut_title_layout)

        bcut_hint = CaptionLabel(
            "必剪接口主要根据 IP 限制调用速率。在此处填入多个代理节点（支持 HTTP / SOCKS5，每行一个），任务处理时会自动轮换代理并自动隔离异常节点，彻底突破 B 接口速率限制。",
            bcut_card
        )
        bcut_hint.setStyleSheet("color: #8e8e9d; font-size: 12px;")
        bcut_layout.addWidget(bcut_hint)

        self.bcut_proxies_edit = PlainTextEdit(bcut_card)
        self.bcut_proxies_edit.setPlaceholderText(
            "一行一个代理节点，支持 HTTP 与 SOCKS5，例如：\n"
            "http://127.0.0.1:10808\n"
            "socks5://Misaka:Misaka@140.238.42.26:8636\n"
            "http://user:password@ip:port"
        )
        self.bcut_proxies_edit.setMinimumHeight(110)
        self.bcut_proxies_edit.textChanged.connect(self.update_bcut_proxy_count)
        bcut_layout.addWidget(self.bcut_proxies_edit)

        # 操作按钮
        bcut_btn_layout = QHBoxLayout()
        bcut_btn_layout.setSpacing(12)

        self.test_bcut_btn = PushButton("批量测试 B 接口代理池", bcut_card)
        self.test_bcut_btn.setIcon(FIF.SYNC)
        self.test_bcut_btn.setMinimumHeight(38)
        self.test_bcut_btn.clicked.connect(self.on_test_bcut_proxies)

        self.save_bcut_btn = PrimaryPushButton("保存代理池配置", bcut_card)
        self.save_bcut_btn.setIcon(FIF.SAVE)
        self.save_bcut_btn.setMinimumHeight(38)
        self.save_bcut_btn.clicked.connect(self.save_bcut_proxies)

        self.clean_bcut_btn = PushButton("一键剔除失效节点", bcut_card)
        self.clean_bcut_btn.setIcon(FIF.DELETE)
        self.clean_bcut_btn.setMinimumHeight(38)
        self.clean_bcut_btn.setEnabled(False)
        self.clean_bcut_btn.clicked.connect(self.clean_invalid_bcut_proxies)

        bcut_btn_layout.addWidget(self.test_bcut_btn)
        bcut_btn_layout.addWidget(self.clean_bcut_btn)
        bcut_btn_layout.addStretch(1)
        bcut_btn_layout.addWidget(self.save_bcut_btn)
        bcut_layout.addLayout(bcut_btn_layout)

        # 实时测试状态提示栏
        self.bcut_test_status_label = BodyLabel("", bcut_card)
        self.bcut_test_status_label.setStyleSheet("color: #0078D4; font-size: 12px;")
        bcut_layout.addWidget(self.bcut_test_status_label)

        # 节点状态详细清单（测试后展示）
        self.bcut_detail_edit = PlainTextEdit(bcut_card)
        self.bcut_detail_edit.setReadOnly(True)
        self.bcut_detail_edit.setPlaceholderText("💡 点击上方「批量测试」后，将在此实时呈现每个节点的连通状态与往返延迟...")
        self.bcut_detail_edit.setMinimumHeight(110)
        bcut_layout.addWidget(self.bcut_detail_edit)

        main_layout.addWidget(bcut_card)

        # 信号连接
        self.preset_combo.currentTextChanged.connect(self.on_preset_changed)

    def on_preset_changed(self, text):
        preset = self.PRESETS.get(text)
        if not preset:
            return
        if text != "自定义兼容服务 (Custom)":
            self.url_edit.setText(preset["base_url"])
            self.model_edit.setText(preset["model"])
        self.preset_hint.setText(preset["hint"])

    def update_key_count(self):
        text = self.key_edit.toPlainText().strip()
        if not text:
            count = 0
        else:
            count = len([k for k in text.splitlines() if k.strip()])
        self.key_count_label.setText(f"当前已配置: {count} 个")

    def update_bcut_proxy_count(self):
        text = self.bcut_proxies_edit.toPlainText().strip()
        if not text:
            count = 0
        else:
            count = len([k for k in text.splitlines() if k.strip()])
        self.bcut_count_label.setText(f"当前已配置: {count} 个代理")

    def _get_config_targets(self):
        """获取所有需要保持同步的配置文件路径"""
        targets = []
        p1 = Path(__file__).resolve().parent / "whisper_config.json"
        targets.append(p1)
        p2 = Path(__file__).resolve().parent.parent / "whisper_config.json"
        if p2 != p1 and p2.parent.is_dir():
            targets.append(p2)
        p3 = Path.cwd() / "whisper_config.json"
        if p3 not in targets:
            targets.append(p3)
        return targets

    def load_config(self):
        targets = self._get_config_targets()
        cfg = {}
        for p in targets:
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    if cfg:
                        break
                except Exception as e:
                    logging.warning(f"读取配置 {p} 失败: {e}")

        base_url = cfg.get("base_url", "https://api.groq.com/openai/v1")
        model = cfg.get("model", "whisper-large-v3-turbo")
        proxy = cfg.get("proxy", "")
        keys = cfg.get("api_key", [])

        if isinstance(keys, str):
            keys = [keys]
        elif not isinstance(keys, list):
            keys = []

        self.url_edit.setText(base_url)
        self.model_edit.setText(model)
        self.proxy_edit.setText(proxy or "")
        self.key_edit.setPlainText("\n".join(keys))
        self.update_key_count()

        # 加载 B 接口代理池
        bcut_proxies = cfg.get("bcut_proxies", [])
        if not bcut_proxies:
            txt_path = Path(__file__).resolve().parent / "bcut_proxies.txt"
            if txt_path.is_file():
                try:
                    with open(txt_path, "r", encoding="utf-8") as f:
                        bcut_proxies = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
                except Exception:
                    pass
        if isinstance(bcut_proxies, str):
            bcut_proxies = [bcut_proxies]
        elif not isinstance(bcut_proxies, list):
            bcut_proxies = []

        self.bcut_proxies_edit.setPlainText("\n".join(bcut_proxies))
        self.update_bcut_proxy_count()

        matched = False
        for name, preset in self.PRESETS.items():
            if preset["base_url"] and preset["base_url"] == base_url.rstrip('/'):
                self.preset_combo.setCurrentText(name)
                self.preset_hint.setText(preset["hint"])
                matched = True
                break
        if not matched:
            self.preset_combo.setCurrentText("自定义兼容服务 (Custom)")
            self.preset_hint.setText(self.PRESETS["自定义兼容服务 (Custom)"]["hint"])

    def save_config(self):
        base_url = self.url_edit.text().strip().rstrip('/')
        model = self.model_edit.text().strip()
        proxy = self.proxy_edit.text().strip()
        raw_keys = self.key_edit.toPlainText().strip()
        keys = [k.strip() for k in raw_keys.splitlines() if k.strip()]

        bcut_raw = self.bcut_proxies_edit.toPlainText().strip()
        bcut_list = [p.strip() for p in bcut_raw.splitlines() if p.strip()]

        if not base_url:
            InfoBar.warning(
                title="提示",
                content="接口地址 (Base URL) 不能为空！",
                duration=3000,
                parent=self
            )
            return

        cfg_data = {
            "api_key": keys,
            "base_url": base_url,
            "model": model,
            "proxy": proxy,
            "bcut_proxies": bcut_list
        }

        saved_any = False
        for p in self._get_config_targets():
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(cfg_data, f, indent=2, ensure_ascii=False)
                saved_any = True
            except Exception as e:
                logging.error(f"写入配置到 {p} 失败: {e}")

        if saved_any:
            InfoBar.success(
                title="保存成功",
                content="大模型接口与密钥配置已成功更新！",
                duration=3000,
                parent=self
            )
        else:
            InfoBar.error(
                title="保存失败",
                content="无法写入配置文件，请检查目录权限。",
                duration=4000,
                parent=self
            )

    def save_bcut_proxies(self):
        bcut_raw = self.bcut_proxies_edit.toPlainText().strip()
        bcut_list = [p.strip() for p in bcut_raw.splitlines() if p.strip()]

        # 1. 更新所有 candidate whisper_config.json
        for p in self._get_config_targets():
            cfg = {}
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    cfg = {}
            cfg["bcut_proxies"] = bcut_list
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logging.error(f"写入 {p} 失败: {e}")

        # 2. 同时写入 bcut_proxies.txt 便于外部管理
        txt_targets = [
            Path(__file__).resolve().parent / "bcut_proxies.txt",
            Path(__file__).resolve().parent.parent / "bcut_proxies.txt",
            Path.cwd() / "bcut_proxies.txt"
        ]
        for tp in txt_targets:
            try:
                tp.parent.mkdir(parents=True, exist_ok=True)
                with open(tp, "w", encoding="utf-8") as f:
                    f.write("# B 接口 (必剪) 专属代理池列表，一行一个\n")
                    for px in bcut_list:
                        f.write(f"{px}\n")
            except Exception:
                pass

        # 3. 内存代理池即时生效
        try:
            from bk_asr.ProxyPool import bcut_proxy_pool
            bcut_proxy_pool.set_proxies(bcut_list)
        except Exception:
            pass

        InfoBar.success(
            title="保存成功",
            content=f"已成功保存 {len(bcut_list)} 个 B 接口代理，已立即注入代理池生效！",
            duration=3000,
            parent=self
        )

    def on_test_bcut_proxies(self):
        bcut_raw = self.bcut_proxies_edit.toPlainText().strip()
        bcut_list = [p.strip() for p in bcut_raw.splitlines() if p.strip()]
        if not bcut_list:
            InfoBar.warning(
                title="提示",
                content="请先在文本框中粘贴至少一个代理节点后再进行测试！",
                duration=3000,
                parent=self
            )
            return

        self.test_bcut_btn.setEnabled(False)
        self.test_bcut_btn.setText(f"正在并发测试 (0/{len(bcut_list)})...")
        self.bcut_test_status_label.setText(f"🚀 已启动多线程并发测试（共 {len(bcut_list)} 个节点），正在向 B 站发起连通探测...")
        self.bcut_test_status_label.setStyleSheet("color: #0078D4; font-size: 12px;")

        self.bcut_test_thread = BcutProxyTestThread(bcut_list)
        self.bcut_test_thread.progress_signal.connect(self.on_bcut_test_progress)
        self.bcut_test_thread.finished_signal.connect(self.on_bcut_test_finished)
        self.bcut_test_thread.start()

    def on_bcut_test_progress(self, done, total, last_info):
        self.test_bcut_btn.setText(f"正在并发测试 ({done}/{total})...")
        self.bcut_test_status_label.setText(f"⚡ 测试进度 ({done}/{total}): {last_info}")

    def on_bcut_test_finished(self, success, fail, summary, results):
        self.test_bcut_btn.setEnabled(True)
        self.test_bcut_btn.setText("批量测试 B 接口代理池")
        self.last_test_results = results

        # 1. 立即将测试结果应用到当前运行时的内存代理池（程序中已标记！）
        try:
            from bk_asr.ProxyPool import bcut_proxy_pool
            bcut_proxy_pool.apply_test_results(results)
        except Exception:
            pass

        # 2. 将详细结果逐行呈现到详情输入框中，清晰标注可用/失效
        detail_lines = []
        for r in results:
            if not r:
                continue
            ok, p, msg = r
            tag = "✅ [可用]" if ok else "❌ [失效]"
            detail_lines.append(f"{tag} {msg}")
        self.bcut_detail_edit.setPlainText("\n".join(detail_lines))

        # 3. 如果存在失效节点，激活「一键剔除失效节点」按钮
        if fail > 0 and success > 0:
            self.clean_bcut_btn.setEnabled(True)
            self.clean_bcut_btn.setText(f"一键剔除失效节点 ({fail} 个)")
        else:
            self.clean_bcut_btn.setEnabled(False)
            self.clean_bcut_btn.setText("一键剔除失效节点")

        if success > 0:
            self.bcut_test_status_label.setText(
                f"✅ 测试完成：{success} 个节点连通正常（已在程序内存中优先标记），{fail} 个节点不可用（已自动隔离）。"
            )
            self.bcut_test_status_label.setStyleSheet("color: #107C41; font-size: 12px; font-weight: bold;")
            InfoBar.success(
                title=f"测试完成 ({success} 可用 / {fail} 失败)",
                content=summary,
                duration=6000,
                parent=self.window()
            )
        else:
            self.bcut_test_status_label.setText(f"❌ 测试失败：全部 {fail} 个节点均未能连通 B 站接口。")
            self.bcut_test_status_label.setStyleSheet("color: #D83B01; font-size: 12px; font-weight: bold;")
            InfoBar.error(
                title=f"全部节点均不可用 ({fail} 个失败)",
                content=summary,
                duration=8000,
                parent=self.window()
            )

    def clean_invalid_bcut_proxies(self):
        """一键剔除所有失效节点，仅保留测试成功的可用节点"""
        if not hasattr(self, 'last_test_results') or not self.last_test_results:
            return

        valid_proxies = [item[1].strip() for item in self.last_test_results if item and item[0]]
        removed_count = len(self.last_test_results) - len(valid_proxies)

        self.bcut_proxies_edit.setPlainText("\n".join(valid_proxies))
        self.update_bcut_proxy_count()
        self.save_bcut_proxies()

        self.clean_bcut_btn.setEnabled(False)
        self.clean_bcut_btn.setText("已剔除失效节点")

        self.bcut_test_status_label.setText(f"🧹 已自动剔除 {removed_count} 个失效节点，当前仅保留 {len(valid_proxies)} 个高可用节点！")
        self.bcut_test_status_label.setStyleSheet("color: #107C41; font-size: 12px; font-weight: bold;")

        InfoBar.success(
            title="清理完成",
            content=f"已剔除 {removed_count} 个超时/失效节点，保留 {len(valid_proxies)} 个可用节点并已保存配置！",
            duration=4000,
            parent=self.window()
        )

    def on_test_connection(self):
        base_url = self.url_edit.text().strip()
        proxy = self.proxy_edit.text().strip()
        raw_keys = self.key_edit.toPlainText().strip()
        keys = [k.strip() for k in raw_keys.splitlines() if k.strip()]
        first_key = keys[0] if keys else ""

        if not base_url:
            InfoBar.warning(
                title="提示",
                content="请先填写接口地址 (Base URL) 后再进行测试！",
                duration=3000,
                parent=self
            )
            return

        self.test_btn.setEnabled(False)
        self.test_btn.setText("正在探测接口...")

        self.test_thread = TestThread(
            base_url=base_url,
            api_key=first_key,
            model=self.model_edit.text().strip(),
            proxy=proxy
        )
        self.test_thread.finished_signal.connect(self.on_test_finished)
        self.test_thread.start()

    def on_test_finished(self, success, message):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("测试当前接口连接")
        if success:
            InfoBar.success(
                title="连通性测试通过",
                content=message,
                duration=4000,
                parent=self
            )
        else:
            InfoBar.error(
                title="连通性测试失败",
                content=message,
                duration=6000,
                parent=self
            )


class MainWindow(FluentWindow):
    """主窗口"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle('音流（VoiceFlow Studio）—— 多引擎并发 AI 语音识别与智能字幕工作台')

        # ASR 处理界面 (顶部工作区)
        self.asr_widget = ASRWidget()
        self.asr_widget.setObjectName("main")
        self.addSubInterface(self.asr_widget, FIF.MEDIA, '转录工作台')

        # 接口配置与代理池 (对齐 D:\mydouyin 侧栏底部停靠结构)
        self.config_widget = ConfigWidget()
        self.config_widget.setObjectName("config")
        self.addSubInterface(self.config_widget, FIF.SETTING, '接口与代理池', position=NavigationItemPosition.BOTTOM)

        # 个人信息与更新 (侧栏底部停靠)
        self.info_widget = InfoWidget()
        self.info_widget.setObjectName("info")
        self.addSubInterface(self.info_widget, FIF.INFO, '关于项目', position=NavigationItemPosition.BOTTOM)

        self.navigationInterface.setExpandWidth(170)
        self.navigationInterface.setReturnButtonVisible(False)
        self.resize(960, 680)
        self.setMinimumSize(900, 620)

        # 注入暗黑深空主题全局样式（完整对齐 D:\mydouyin 配色体系）
        self.setStyleSheet("""
            FluentWindow, QWidget#stackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {
                background-color: #0e0e14;
            }
            FluentTitleBar {
                background-color: #0e0e14;
            }
            FluentTitleBar > QLabel#titleLabel {
                color: #8c8c9e;
                font-size: 12px;
                font-weight: 500;
                padding-left: 8px;
            }
            NavigationInterface {
                background-color: #121218;
                border-right: 1px solid rgba(255, 255, 255, 0.06);
            }
        """)

        self.update_checker = UpdateCheckerThread(self)
        self.update_checker.msg.connect(self.show_msg)
        self.update_checker.start()

    def show_msg(self, title, content, update_download_url):
        w = MessageBox(title, content, self)
        if w.exec() and update_download_url:
            webbrowser.open(update_download_url)
        if title == "更新":
            sys.exit(0)

def video2audio(input_file: str, output: str = "") -> bool:
    """使用ffmpeg将视频转换为音频"""
    # 创建output目录
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output = str(output)

    ffmpeg_exe = "ffmpeg"
    local_ffmpeg = Path(__file__).resolve().parent / "ffmpeg.exe"
    if not local_ffmpeg.exists():
        local_ffmpeg = Path(__file__).resolve().parent.parent / "ffmpeg.exe"
    if local_ffmpeg.exists():
        ffmpeg_exe = str(local_ffmpeg)

    cmd = [
        ffmpeg_exe,
        '-i', input_file,
        '-vn',
        '-ar', '16000',
        '-ac', '1',
        '-b:a', '48k',
        '-f', 'mp3',
        '-af', 'aresample=async=1',
        '-y',
        output
    ]
    kwargs = {
        'capture_output': True,
        'check': True,
        'encoding': 'utf-8',
        'errors': 'replace'
    }
    if platform.system() == 'Windows':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs['startupinfo'] = startupinfo
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

    result = subprocess.run(cmd, **kwargs)

    if result.returncode == 0 and Path(output).is_file():
        return True
    else:
        return False

def start():
    # enable dpi scale
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    setTheme(Theme.DARK)
    setThemeColor(QColor("#FE2C55"))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    start()
