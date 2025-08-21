import sys
import threading
from pathlib import Path

from PySide6.QtWidgets import (QApplication, QLineEdit, QPushButton, 
                               QTableWidget, QMessageBox, 
                               QHeaderView, QTableWidgetItem,QDialog, QProgressBar,
                               QVBoxLayout, QLabel, QFileDialog)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QObject, Signal, Slot, Qt

from core.downloader import Downloader
from core.spider import DouyinSpider
from PySide6.QtWidgets import QFileDialog
import os
import time
import re


class MainWindow(QObject):
    """主窗口控制器"""
    # 自定义信号，用于从后台线程安全更新UI，所有通过后台线程操作UI的地方都需要使用这些信号，避免程序卡死
    update_table_signal = Signal(list)  # 参数为视频列表
    update_row_signal = Signal(int, object)  # 参数为行索引和VideoItem
    show_info_signal = Signal(str, str)  # 信息提示信号(标题, 消息)
    show_error_signal = Signal(str, str)  # 参数为标题和错误消息
    create_operation_dialog_signal = Signal(str,str, bool, bool)  # 参数为窗口标题，消息文本, 是否添加确认按钮, 是否添加取消按钮
    close_operation_dialog_signal = Signal()  # 关闭操作弹窗信号

    def __init__(self):
        super().__init__()
        # 加载UI文件
        self.loader = QUiLoader()
        ui_path = Path(__file__).parent / "ui" / "main_window.ui"
        self.window = self.loader.load(str(ui_path))
        # 判断是否是打包环境
        if getattr(sys, 'frozen', False):
            # 打包后，UI文件在临时目录的ui文件夹下
            base_path = Path(sys._MEIPASS)
        else:
            # 开发环境，使用原路径
            base_path = Path(__file__).parent
            
        ui_path = base_path / "ui" / "main_window.ui"
        self.window = self.loader.load(str(ui_path))

        # 初始化爬虫实例(创建类实例)
        self.spider = DouyinSpider()
        self.video_items = []  # 存储视频项的列表

        # 添加下载管理相关属性
        self.downloader = None
        self.cancel_download = False
        self.download_dialog = None
        self.download_progress_label = None
        self.download_cancel_button = None

        # 添加操作弹窗相关属性
        self.operation_dialog = None  # 当前操作弹窗引用
        self.operation_type = None    # 当前操作类型（login/favorites/likes）
        self.operation_cancelled = False  # 操作取消标志      

        # 获取UI控件
        self.url_input = self.window.findChild(QLineEdit, "url_input")
        self.btn_resolution = self.window.findChild(QPushButton, "btn_resolution")
        self.btn_favorites = self.window.findChild(QPushButton, "btn_favorites")
        self.btn_likes = self.window.findChild(QPushButton, "btn_likes")
        self.table_widget = self.window.findChild(QTableWidget, "table_widget")
        self.btn_select_file = self.window.findChild(QPushButton, "btn_select_file")
        self.btn_download = self.window.findChild(QPushButton, "btn_download")
        self.save_directory = self.window.findChild(QLineEdit, "save_directory")
        self.btn_login = self.window.findChild(QPushButton, "btn_login")  # 需要在UI文件中添加此按钮

        # 设置默认保存路径
        self.set_default_download_path()                             

        # 初始化UI
        self.init_table()
        
        # 连接信号槽
        self.btn_resolution.clicked.connect(self.resolve_url)
        self.btn_favorites.clicked.connect(self.get_favorites) #调用spider类中的方法
        self.btn_likes.clicked.connect(self.get_likes)
        self.btn_select_file.clicked.connect(self.save_path)
        self.btn_download.clicked.connect(self.download_videos)
        self.btn_login.clicked.connect(self.perform_login)
        
        # 连接自定义信号
        self.update_table_signal.connect(self.update_table)
        self.update_row_signal.connect(self.update_table_row)
        self.show_error_signal.connect(self.show_error_message)
        self.show_info_signal.connect(self.show_info_message)
        self.create_operation_dialog_signal.connect(self.create_operation_dialog)
        self.close_operation_dialog_signal.connect(self._close_operation_dialog)

        
        # 连接下载管理器的信号
        # self.download.finished.connect(self.download_completed)
  
    def init_table(self):
        """初始化表格设置"""
        headers = ["标题", "URL"]
        # 设置表格的列数。len(headers)获取headers列表的长度(这里是2)，所以表格会有2列。
        self.table_widget.setColumnCount(len(headers))
        # 设置表格的水平表头(列标题)为headers列表中的内容，即第一列标题为"标题"，第二列标题为"URL"。
        self.table_widget.setHorizontalHeaderLabels(headers)
        
        # 设置列宽
        # self.table_widget.setColumnWidth(0, 50)   # 序号列
        self.table_widget.setColumnWidth(0, 1000)  # 标题列
        self.table_widget.setColumnWidth(1, 1000)  # URL列
        
        # 设置表头自适应
        # horizontalHeader()：这个方法返回表格的水平表头（QHeaderView 对象），控制表格的列。
        # setSectionResizeMode(column, mode)：这个方法设置指定列的调整模式。
        # QHeaderView.ResizeMode.Stretch：这个模式表示列会自动调整宽度以填充整个表格宽度。
        self.table_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # 标题列自适应
        self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # URL列自适应



    def resolve_url(self):
        """解析URL按钮点击事件"""
        text = self.url_input.text().strip()
        url = self.extract_douyin_url(text)
        print(f"提取的URL为:{url}")

        if not url:
            QMessageBox.warning(self.window, "警告", "请输入抖音链接,支持解析单个视频链接或用户主页链接")
            return
        
        # 设置操作类型
        self.operation_type = "resolve"
        self.operation_cancelled = False
        self.spider.cancel_flag = False
        # 创建操作弹窗
        self.create_operation_dialog_signal.emit(
            "解析URL",
            "正在解析URL下的视频信息...",
            True,
            False
        )
        
        # 启动新线程执行解析操作
        threading.Thread(
            target=self._resolve_url_thread, 
            args=(url,), 
            daemon=True
        ).start()
    
    def _resolve_url_thread(self, url):
        """在后台线程中解析URL"""
        try:            
            # 将输入的URL传递给spider的resolve_url方法解析，得到最终的URL，该方法将抖音的URL短链转化为最终的跳转URL
            final_url = self.spider.resolve_url(url)
            if final_url is None:
                self.close_operation_dialog_signal.emit()
                self.show_error_signal.emit("错误", "无法解析URL，请检查链接是否正确")
                return
            
            if "/video/" in final_url:
                video_items = self.spider.get_single_video(final_url)
                # 检查是否获取到视频项目,如果没有，弹出提示
                if not video_items:  # 空列表判断
                    self.close_operation_dialog_signal.emit()
                    # 弹出警告框
                    self.show_error_signal.emit("警告", "未能获取视频信息，请检查链接或重试！")

                else:
                    # 更新表格
                    self.close_operation_dialog_signal.emit()
                    self.update_table_signal.emit(video_items)
                
            elif "/user/" in final_url:
                if "/user/self" in final_url:
                    self.close_operation_dialog_signal.emit()
                    self.show_error_signal.emit("警告", "请勿使用自己的主页链接，仅支持解析他人主页链接")
                    return                         
                
                video_items = self.spider.get_user_videos(final_url)
                # 检查返回值是否为字符串(错误信息)
                if isinstance(video_items, str):
                    # 如果是错误信息，通过self.show_error_signal.emit()发送一个错误信号，显示提示信息。
                    self.close_operation_dialog_signal.emit()
                    self.show_error_signal.emit("提示", video_items)
                else:
                    # 如果不是字符串（可能是视频列表数据），则通过self.update_table_signal.emit()发送更新表格的信号，将视频数据传递给UI进行显示。
                    self.update_table_signal.emit(video_items)
                    self.close_operation_dialog_signal.emit()
            else:
                self.close_operation_dialog_signal.emit()
                # 使用信号在主线程中显示错误消息
                self.show_error_signal.emit("警告", "请输入正确的抖音链接")
                self.update_table_signal.emit([])  # 清空表格
                return #这里的 return 语句表示从当前函数立即退出，不再执行后续代码。
            
            # 发送信号更新表格（在主线程中执行）
            self.update_table_signal.emit(video_items)
            
        except Exception as e:
            # 错误处理：在主线程显示错误消息
            error_msg = f"解析失败: {str(e)}"
            self.close_operation_dialog_signal.emit()
            self.show_error_signal.emit("错误", error_msg)
            self.update_table_signal.emit([])  # 清空表格
            

    def extract_douyin_url(self, text):
        # 优先匹配抖音短链接格式
        short_pattern = r'https://v\.douyin\.com/\S+[/]?'
        short_match = re.search(short_pattern, text)
        
        if short_match:
            return short_match.group(0).rstrip('/')  # 去除可能的多余斜杠
        
        # 如果没有短链接，尝试匹配普通抖音链接
        normal_pattern = r'https://www\.douyin\.com/\S+[/]?'
        normal_match = re.search(normal_pattern, text)
        
        if normal_match:
            return normal_match.group(0).rstrip('/')  # 去除可能的多余斜杠
        
        # 如果都没有匹配到，返回空字符串
        return ""
    def get_favorites(self):
        """处理收藏按钮点击事件"""
        # 设置操作类型
        self.operation_type = "favorites"
        self.operation_cancelled = False
        self.spider.cancel_flag = False
        
        # 创建操作弹窗
        self.create_operation_dialog_signal.emit(
            "获取收藏视频",
            "正在获取我的收藏下的所有视频...",
            True,
            False
        )
        
        # 启动新线程执行操作
        threading.Thread(
            target=self._get_favorites_thread,
            daemon=True
        ).start()

    def _get_favorites_thread(self):
        """在后台线程中获取收藏视频"""
        try:
            # 阶段1: 检查登录状态
            # 检查操作是否被取消
            if self.operation_cancelled:
                return           
            # 创建不可见浏览器headless=True,调试时可以设置headless=False
            self.spider.create_browser(headless=True)
            
            # 检查登录状态
            is_logged_in = self.spider.check_login_status()
              
            if not is_logged_in:
                # ✅ 使用信号关闭操作弹窗
                self.close_operation_dialog_signal.emit()
                # 未登录状态处理，弹出提示信息
                self.show_error_signal.emit(
                    "需要登录", 
                    "需要登录才能获取收藏视频\n请先点击右上角的'登录'按钮完成登录"
                )
                return

            # 阶段2: 获取收藏视频            
            # 传递取消标志给爬虫
            video_items = self.spider.get_favorites_videos()
            
            # 检查操作是否被取消
            if isinstance(video_items, str):
                # 如果是错误信息，通过self.show_error_signal.emit()发送一个错误信号，显示提示信息。
                self.show_error_signal.emit("提示", video_items)
            else:
                # 如果不是字符串（可能是视频列表数据），则通过self.update_table_signal.emit()发送更新表格的信号，将视频数据传递给UI进行显示。
                self.update_table_signal.emit(video_items)
           
        except Exception as e:
            # 异常处理：仅在没有取消操作时显示错误
            if not self.operation_cancelled:
                error_msg = f"获取收藏视频失败: {str(e)}"
                self.show_error_signal.emit("错误", error_msg)
        finally:
            self.spider.close_browser()
            self.close_operation_dialog_signal.emit()

    def get_likes(self):
        """处理喜欢按钮点击事件"""
        # 设置操作类型
        self.operation_type = "likes"
        self.operation_cancelled = False
        self.spider.cancel_flag = False
        
        # 创建操作弹窗
        self.create_operation_dialog_signal.emit(
            "获取喜欢视频",
            "正在获取我的喜欢下的所有视频...",
            True,
            False
        )
        
        # 启动后台线程
        threading.Thread(
            target=self._get_likes_thread,
            daemon=True
        ).start()

    def _get_likes_thread(self):
        """在后台线程中获取喜欢视频"""
        try:
            # 阶段1: 检查登录状态
            # 检查操作是否被取消
            if self.operation_cancelled:
                return
            # 创建不可见浏览器
            self.spider.create_browser(headless=True)
            
            # 检查登录状态
            is_logged_in = self.spider.check_login_status()
        
            if not is_logged_in:
                # 未登录状态处理
                self.close_operation_dialog_signal.emit()
                self.show_error_signal.emit(
                    "需要登录", 
                    "需要登录才能获取收藏视频\n请先点击右上角的'登录'按钮完成登录"
                )
                return

            # 阶段2: 获取喜欢视频           
            # 传递取消标志给爬虫
            video_items = self.spider.get_likes_videos()
            
            # 检查操作是否被取消
            if isinstance(video_items, str):
                # 如果是错误信息，通过self.show_error_signal.emit()发送一个错误信号，显示提示信息。
                self.show_error_signal.emit("提示", video_items)
            else:
                # 如果不是字符串（可能是视频列表数据），则通过self.update_table_signal.emit()发送更新表格的信号，将视频数据传递给UI进行显示。
                self.update_table_signal.emit(video_items)
           
        except Exception as e:
            # 异常处理：仅在没有取消操作时显示错误
            if not self.operation_cancelled:
                error_msg = f"获取收藏视频失败: {str(e)}"
                self.show_error_signal.emit("错误", error_msg)
        finally:
            self.spider.close_browser()
            self.close_operation_dialog_signal.emit()

    def perform_login(self):
        """处理登录按钮点击事件"""

        # 设置操作类型
        self.operation_type = "login"
        self.operation_cancelled = False
        self.spider.cancel_flag = False
        
        # 创建操作弹窗
        self.create_operation_dialog_signal.emit(
            "登录操作",
            "正在执行登录操作，请在浏览器中操作，登录成功后将自动关闭浏览器。",
            True,
            False
        )
        # 启动登录监控线程
        self.login_monitoring = True  # 监控状态标志
        """
        login_monitoring是一个标志位，用于控制登录监控线程的运行状态。
        为什么需要这个标志？
        直接终止线程（如thread.terminate()）会导致：
            可能使浏览器资源未正确释放
            可能引发僵尸进程
            破坏程序状态一致性
        而通过标志位控制可实现：
            ✅ 安全优雅的线程退出
            ✅ 跨线程状态同步
            ✅ 资源清理的确定性
        提示：在多线程编程中，这种通过标志位控制循环退出的模式被称为"graceful shutdown"（优雅退出），是并发编程的最佳实践之一。    
        """
        threading.Thread(
            target=self._login_monitoring_thread,
            # 将线程设置为守护线程（daemon thread）守护线程的特点是：当主程序结束时，守护线程会自动终止，不管它是否执行完成，这对于后台监控任务很有用，可以确保程序退出时不会因为线程未结束而卡住
            daemon=True
        ).start()
        
    def _login_monitoring_thread(self):
        """登录监控线程"""
        try:
            if self.operation_cancelled:
                return
            # 创建可见浏览器
            self.spider.create_browser(False)            
            
            # 计时器
            start_time = time.time()
            check_interval = 3  # 检查间隔(秒)
            timeout = 60  # 超时时间(秒)
            
            # 检测循环
            while self.login_monitoring and not self.operation_cancelled:
                # 检查浏览器是否已关闭
                if not self.spider.page.states.is_alive:
                    self.close_operation_dialog_signal.emit()
                    self.show_error_signal.emit(
                        "错误","浏览器意外关闭，请重新操作登录"
                    )
                    return
                
                # 检查登录状态
                if self.spider.check_login_status():
                    self.close_operation_dialog_signal.emit()
                    # 登录成功
                    self.show_info_signal.emit(
                        "提示","已登录成功！"
                    )
                    return
                
                # 检查是否超时
                elapsed_time = time.time() - start_time
                if elapsed_time > timeout:
                    self.close_operation_dialog_signal.emit()                    
                    self.show_error_signal.emit(
                        "错误","超时未登录，请重新操作"
                    )
                    return
                
                # 等待下一次检查
                time.sleep(check_interval)
        
        except Exception as e:
            # 如果操作被取消，不显示错误信息
            if not self.operation_cancelled:
                self.show_error_signal.emit(
                    "错误",f"登录过程出错: {str(e)}"
                )
        finally:
            # 确保清理
            self.login_monitoring = False
            self.spider.close_browser()


    def create_operation_dialog(self, title, message, cancellable=True, confirmable=False):
        """
        创建通用操作弹窗
        :param title: 弹窗标题
        :param message: 初始消息文本
        :param cancellable: 是否显示取消按钮
        :param confirmable: 是否显示确认按钮
        """
        # 关闭现有弹窗（如果有）
        if self.operation_dialog:
            self.operation_dialog.close()
            self.operation_dialog = None
            
        # 创建新弹窗
        self.operation_dialog = QMessageBox(self.window)
        self.operation_dialog.setWindowTitle(title)
        self.operation_dialog.setText(message)
        self.operation_dialog.setFixedSize(400, 150)
        
        # 设置按钮
        buttons = QMessageBox.StandardButton.NoButton
        if cancellable and confirmable:
            buttons = QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok
        elif cancellable:
            buttons = QMessageBox.StandardButton.Cancel
        elif confirmable:
            buttons = QMessageBox.StandardButton.Ok
            
        self.operation_dialog.setStandardButtons(buttons)
        
        # 配置按钮文本和事件
        if cancellable:
            cancel_button = self.operation_dialog.button(QMessageBox.StandardButton.Cancel)
            cancel_button.setText("取消")
            cancel_button.clicked.connect(self._cancel_operation)
            
        if confirmable:
            confirm_button = self.operation_dialog.button(QMessageBox.StandardButton.Ok)
            confirm_button.setText("确定")
            confirm_button.clicked.connect(self._confirm_operation)
        
        # 设置为模态对话框
        self.operation_dialog.setModal(True)
        
        # 显示弹窗
        self.operation_dialog.show()
        
        return self.operation_dialog

    def _close_operation_dialog(self):
        """安全关闭操作弹窗"""
        if self.operation_dialog:
            self.operation_dialog.close()
            self.operation_dialog.deleteLater()
            self.operation_dialog = None
        self.set_ui_enabled(True)

    def _cancel_operation(self):
        """处理操作取消"""
        # 设置取消标志
        self.spider.cancel_flag = True
        self.operation_cancelled = True
        
        # 根据操作类型执行不同的取消处理
        if self.operation_type == "login":
            # 登录操作取消
            try:
                self.spider.close_browser()
            except Exception as e:
                print(f"关闭浏览器时出错: {str(e)}")
            self.show_info_signal.emit("操作取消", "登录操作已取消")           
        elif self.operation_type in ["favorites", "likes" ,"resolve"]:
            # 收藏/喜欢操作取消
            self.show_info_signal.emit("操作取消", "获取操作已取消")
        
        # 关闭弹窗
        self.close_operation_dialog_signal.emit()
        

    def _confirm_operation(self):
        """处理操作确认"""
        # 设置操作取消标志，防止后台线程继续执行
        self.operation_cancelled = True
        # 关闭弹窗
        self.close_operation_dialog_signal.emit()
        
    def set_ui_enabled(self, enabled):
        """
        设置UI控件的启用状态
        :param enabled: 布尔值，True表示启用控件，False表示禁用控件
        """
        # 主要功能按钮
        self.btn_favorites.setEnabled(enabled)
        self.btn_likes.setEnabled(enabled)
        self.btn_resolution.setEnabled(enabled)
        self.btn_download.setEnabled(enabled)
        self.btn_login.setEnabled(enabled)  # 如果存在登录按钮
        self.btn_select_file.setEnabled(enabled)  # 如果存在选择路径按钮
        
        # 输入控件
        self.url_input.setEnabled(enabled)
        self.save_directory.setEnabled(enabled)  # 如果存在保存路径输入框
        
        # 表格控件
        self.table_widget.setEnabled(enabled)
        
        # 调整按钮文本
        self.btn_resolution.setText("解析")
        self.btn_download.setText("下载")
    
    def set_default_download_path(self):
        """设置默认下载路径"""
        # 获取用户下载目录
        download_path = os.path.expanduser("~\Downloads")
        
        # 检查路径是否存在，如果不存在则使用用户主目录
        if not os.path.exists(download_path):
            download_path = os.path.expanduser("~")
        
        # 设置控件文本
        self.save_directory.setText(download_path)

    def save_path(self):
        """打开文件夹选择对话框"""
        path = QFileDialog.getExistingDirectory(self.window, "选择保存路径")
        if path:
            self.save_directory.setText(path)

    @Slot(list)
    def update_table(self, video_items):
        """更新整个表格（在主线程执行）"""
        self.video_items = video_items
        self.table_widget.setRowCount(len(video_items))
        
        # 更新每一行
        for i, video in enumerate(video_items):
            self.update_table_row(i, video)
    
    @Slot(int, object)
    def update_table_row(self, row_index, video_item):
        """更新表格的某一行（在主线程执行）"""

        # 标题列
        title_item = self.table_widget.item(row_index, 0)
        if title_item is None:
            title_item = QTableWidgetItem()
            self.table_widget.setItem(row_index, 0, title_item)
        title_item.setText(video_item.title)
        title_item.setToolTip(video_item.title)  # 添加悬停提示
        
        # URL列
        url_item = self.table_widget.item(row_index, 1)
        if url_item is None:
            url_item = QTableWidgetItem()
            self.table_widget.setItem(row_index, 1, url_item)
        url_item.setText(video_item.url)
        url_item.setToolTip(video_item.url)  # 添加悬停提示

    @Slot(str, str)
    def show_info_message(self, title, message):
        """显示信息消息对话框"""
        QMessageBox.information(self.window, title, message)
        
    @Slot(str, str)
    def show_error_message(self, title, message):
        """显示错误消息对话框"""
        # # Qt 标准消息框类型
        # QMessageBox.information()  # 信息框
        # QMessageBox.warning()      # 警告框
        # QMessageBox.critical()     # 错误框
        # QMessageBox.question()     # 问题框
        QMessageBox.critical(self.window, title, message)

    def show(self):
        """显示窗口"""
        self.window.show()

    def download_videos(self):
        """启动下载过程"""
        save_path = self.save_directory.text()
        
        # 验证路径
        if not save_path or not os.path.isdir(save_path):
            QMessageBox.warning(self.window, "路径错误", "请选择有效的保存路径")
            return
        
        if not self.video_items:
            QMessageBox.warning(self.window, "错误", "没有可下载的视频")
            return
        
        # 创建下载弹窗
        self._create_download_dialog()
        
        # 禁用主窗口按钮
        self.set_ui_enabled(False)
        
        # 重置取消标志
        self.cancel_download = False
        
        # 创建并启动下载线程
        self.downloader = Downloader(self.video_items, save_path)

        # 连接信号
        try:
            self.downloader.finished.disconnect()
            self.downloader.error.disconnect()
            self.downloader.progress.disconnect()
        except:
            pass
            
        self.downloader.finished.connect(self.download_completed)
        self.downloader.error.connect(self.download_failed)
        self.downloader.progress.connect(self._update_download_progress)
        self.downloader.start()

    def _create_download_dialog(self):
        """创建下载进度弹窗"""
        # 检查是否已存在下载对话框（self.download_dialog），如果存在则先关闭它
        if self.download_dialog is not None:
            self.download_dialog.close()
            
        self.download_dialog = QDialog(self.window)
        self.download_dialog.setWindowTitle("下载进度")
        # 设置为模态对话框（setModal(True)），这意味着显示此对话框时会阻止用户与其他窗口交互
        self.download_dialog.setModal(True)
        # 固定对话框大小为400x150像素
        self.download_dialog.setFixedSize(400, 150)
        
        # 进度标签
        self.download_progress_label = QLabel("正在准备下载...", self.download_dialog)
        # 使用setAlignment(Qt.AlignCenter)使文本居中显示
        self.download_progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
  
        # 进度条,创建了一个QProgressBar进度条对象
        self.progress_bar = QProgressBar(self.download_dialog)
        # 设置进度条的范围，从0到总视频数量
        self.progress_bar.setRange(0, len(self.video_items))
        # 初始化进度条值为0
        self.progress_bar.setValue(0)
                
        # 取消按钮,创建了一个QPushButton按钮对象，并连接了点击事件
        self.download_cancel_button = QPushButton("取消下载", self.download_dialog)
        # 将按钮点击信号与_cancel_download槽函数连接
        self.download_cancel_button.clicked.connect(self._cancel_download)

        # 先创建组件后布局，弹窗布局设置：垂直布局
        layout = QVBoxLayout(self.download_dialog)
        # 将标签添加到布局中才能显示
        layout.addWidget(self.download_progress_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.download_cancel_button)
        
        # 展示弹窗
        self.download_dialog.show()
    
    def _update_download_progress(self, current, total, success):
        """更新下载进度"""
        if self.download_progress_label:
            # 根据success参数设置状态文本（"成功"或"失败"），并将当前进度、总数和状态组合成字符串显示在标签上。
            status = "成功" if success else "失败"
            self.download_progress_label.setText(
                f"正在下载: {current}/{total} ({status})"
            )
            # 更新进度条的当前值，直观展示下载进度
            self.progress_bar.setValue(current)
            
            # 表格数据自动滚动到最后，确保用户可以看到最新的下载进度信息
            self.table_widget.scrollToBottom()

    def _cancel_download(self):
        """取消下载操作"""
        self.cancel_download = True
        if self.downloader:
            self.downloader.cancel()
        
        if self.download_dialog:
            self.download_dialog.close()
            self.download_dialog = None
            
        self.set_ui_enabled(True)        
        QMessageBox.information(self.window, "下载取消", "下载操作已取消")

    @Slot(int)  # 添加参数类型
    def download_completed(self, success_count):
        """下载完成处理"""
        if self.download_dialog:
            self.download_dialog.close()
            self.download_dialog = None
            
        self.set_ui_enabled(True)     
        QMessageBox.information(
            self.window, 
            "完成", 
            f"下载完成！成功下载 {success_count}/{len(self.video_items)} 个视频。"
        )
        
    def download_failed(self, error_msg):
        """下载失败处理"""
        if self.download_dialog:
            self.download_dialog.close()
            self.download_dialog = None
            
        self.set_ui_enabled(True)      
        QMessageBox.critical(self.window, "下载错误", f"下载失败: {error_msg}")
        
        # 确保断开 finished 信号，避免触发 download_completed
        try:
            self.downloader.finished.disconnect(self.download_completed)
        except:
            pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())