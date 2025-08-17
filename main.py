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



class MainWindow(QObject):
    """主窗口控制器"""
    # 自定义信号，用于从后台线程安全更新UI
    update_table_signal = Signal(list)  # 参数为视频列表
    update_row_signal = Signal(int, object)  # 参数为行索引和VideoItem
    show_error_signal = Signal(str, str)  # 参数为标题和错误消息
    update_button_signal = Signal(bool, str, str)  # 参数为启用状态和按钮文本和按钮ID
    update_login_dialog_signal = Signal(str, bool)  # 参数为消息文本和是否添加确认按钮

    def __init__(self):
        super().__init__()
        # 加载UI文件
        self.loader = QUiLoader()
        ui_path = Path(__file__).parent / "ui" / "main_window.ui"
        self.window = self.loader.load(str(ui_path))
        # 初始化爬虫实例(创建类实例)
        self.spider = DouyinSpider()

        # 添加下载管理相关属性
        self.downloader = None
        self.cancel_download = False
        self.download_dialog = None
        self.download_progress_label = None
        self.download_cancel_button = None

        

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
        
        # 添加窗口关闭事件处理
        self.window.closeEvent = self.handle_close_event

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
        self.update_button_signal.connect(self.update_button_state)
        self.update_login_dialog_signal.connect(self._update_login_dialog_ui)
        
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
        # QHeaderView.Stretch：这个模式表示列会自动调整宽度以填充整个表格宽度。
        self.table_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)  # 标题列自适应
        self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)  # URL列自适应

    def perform_login(self):
        """处理登录按钮点击事件"""
        # 创建进度对话框
        self.login_dialog = QMessageBox(self.window)    # 创建一个消息对话框，self.window是对话框的父窗口
        self.login_dialog.setWindowTitle("登录操作")
        self.login_dialog.setText("正在执行登录操作，请在浏览器中操作，登录成功后将自动关闭浏览器。")
        self.login_dialog.setStandardButtons(QMessageBox.NoButton)
        self.login_dialog.setModal(True)  # 模态对话框，阻止其他窗口操作
        
        # 显示对话框
        self.login_dialog.show()

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
            # 创建可见浏览器
            self.spider.create_browser()            
            
            # 计时器
            start_time = time.time()
            check_interval = 5  # 检查间隔(秒)
            timeout = 60  # 超时时间(秒)
            
            # 检测循环
            while self.login_monitoring:
                # 检查浏览器是否已关闭
                if not self.spider.page.states.is_alive:
                    self._update_login_dialog("浏览器意外关闭，请重新操作登录", True)
                    return
                
                # 检查登录状态
                if self.spider.check_login_status():
                    # 登录成功
                    self._update_login_dialog("已登录成功！", True)
                    return
                
                # 检查是否超时
                elapsed_time = time.time() - start_time
                if elapsed_time > timeout:
                    self.spider.close_browser()
                    self._update_login_dialog("超时未登录，请重新操作", True)
                    return
                
                # 等待下一次检查
                time.sleep(check_interval)
        
        except Exception as e:
            try:
                if hasattr(self.spider, 'page') and self.spider.page:
                    self.spider.close_browser()
            except:
                pass
            self._update_login_dialog(f"登录过程出错: {str(e)}", True)
            # 异常处理
            try:
                self.spider.page.quit()
            except:
                pass
            self._update_login_dialog(f"登录过程出错: {str(e)}", True)

    def _update_login_dialog(self, message, add_ok_button=False):
        """更新登录对话框内容"""
        # 使用信号在主线程中更新UI
        # 这里使用信号槽机制，将更新UI的操作放到主线程中执行，避免多线程直接操作UI导致的错误。
        # 检查当前对象是否具有login_dialog属性，并且该属性不为None（即对话框已存在）
        if hasattr(self, 'login_dialog') and self.login_dialog:
            # 停止监控
            self.login_monitoring = False
            
            # 发送信号更新对话框,这是方法的核心部分，通过发射信号update_login_dialog_signal来更新对话框内容。emit方法会触发连接到这个信号的槽函数，并将message和add_ok_button作为参数传递给槽函数。槽函数会在主线程中执行，从而安全地更新UI。
            self.update_login_dialog_signal.emit(message, add_ok_button)

    def get_favorites(self):
        """处理收藏按钮点击事件"""
        # 检查登录状态,如果未登录，则跳出函数
        if not self.check_and_login("获取收藏视频"):
            return
        
        # 禁用按钮，防止重复点击
        self.btn_favorites.setEnabled(False)
        self.btn_favorites.setText("获取中...")
        
        # 启动新线程执行操作
        threading.Thread(
            target=self._get_favorites_thread,
            args=(),
            daemon=True
        ).start()
    def check_and_login(self,action_name="继续操作"):
        """
        检查登录状态，如果未登录则提示用户登录
        action_name: 用于提示信息中显示的操作名称
        返回: 布尔值，表示是否已登录

        风险:该方法中创建了QMessageBox(一个 GUI 对象),如果在子线程中调用该方法,可能会导致UI线程阻塞,从而影响程序响应。因此,在子线程中调用该方法时,需要修改此方法的实现,将UI更新操作放到主线程中执行。
        """
        
        # 创建不可见浏览器
        self.spider.create_browser(headless=True)  
        # 检查登录状态
        is_logged_in = self.spider.check_login_status()
        
        if not is_logged_in:
            # 创建自定义按钮文本的消息框
            msgBox = QMessageBox(self.window)
            msgBox.setWindowTitle("登录提示")
            msgBox.setText(f"要{action_name}需要先登录抖音账号。")
            msgBox.setStandardButtons(QMessageBox.Ok)
            msgBox.button(QMessageBox.Ok).setText("确定")
            msgBox.exec()
            return False
        return True # 已经是登录状态

    def _get_favorites_thread(self):
        """在后台线程中获取收藏视频"""
        try:
            video_items = self.spider.get_favorites_videos()
            # 检查返回值是否为字符串(错误信息)
            if isinstance(video_items, str):
                # 如果是错误信息，通过self.show_error_signal.emit()发送一个错误信号，显示提示信息。
                self.show_error_signal.emit("提示", video_items)
            else:
                # 如果不是字符串（可能是视频列表数据），则通过self.update_table_signal.emit()发送更新表格的信号，将视频数据传递给UI进行显示。
                self.update_table_signal.emit(video_items)
        except Exception as e:
            self.show_error_signal.emit("错误", f"获取收藏视频失败: {str(e)}")
        finally:
            self.update_button_signal.emit(True, "我的收藏", "btn_favorites")

    def get_likes(self):
        """处理喜欢按钮点击事件"""
        # 检查登录状态
        if not self.check_and_login("获取喜欢视频"):
            return
        
        # 禁用按钮，防止重复点击
        self.btn_likes.setEnabled(False)
        self.btn_likes.setText("获取中...")
        
        # 启动新线程执行操作
        threading.Thread(
            target=self._get_likes_thread,
            args=(),
            daemon=True
        ).start()

    def _get_likes_thread(self):
        """在后台线程中获取喜欢视频"""
        try:
            video_items = self.spider.get_likes_videos()
            # 检查返回值是否为字符串(错误信息)
            if isinstance(video_items, str):
                self.show_error_signal.emit("提示", video_items)
            else:
                self.update_table_signal.emit(video_items)
        except Exception as e:
            self.show_error_signal.emit("错误", f"获取喜欢视频失败: {str(e)}")
        finally:
            self.update_button_signal.emit(True, "我的喜欢", "btn_likes")


    def handle_close_event(self, event):
        """处理窗口关闭事件"""
        print("正在关闭程序，清理资源...")
        # 关闭爬虫浏览器实例
        if hasattr(self, 'spider') and self.spider:
            try:
                self.spider.close_browser()  
            except Exception as e:
                print(f"关闭浏览器时出错: {e}")
        # 接受关闭事件
        event.accept()
    
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

    def resolve_url(self):
        """解析URL按钮点击事件"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self.window, "警告", "请输入抖音链接")
            return
        
        # 禁用按钮，防止重复点击
        self.btn_resolution.setEnabled(False)
        self.btn_resolution.setText("解析中...")
        
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
                self.show_error_signal.emit("错误", "无法解析URL，请检查链接是否正确")
                return
            
            if "/video/" in final_url:
                video_items = self.spider.get_single_video(final_url)
                # 检查是否获取到视频项目,如果没有，弹出提示
                if not video_items:  # 空列表判断
                    # 弹出警告框
                    self.show_error_signal.emit("警告", "未能获取视频信息，请检查链接或重试！")

                else:
                    # 更新表格
                    self.update_table_signal.emit(video_items)
                
            elif "/user/" in final_url:
                if "/user/self" in final_url:
                    self.show_error_signal.emit("警告", "请勿使用自己的主页链接，请使用他人主页链接")
                    return
                video_items = self.spider.get_user_videos(final_url)
                self.update_table_signal.emit(video_items)

            else:
                # 使用信号在主线程中显示错误消息
                self.show_error_signal.emit("警告", "请输入正确的抖音链接")
                self.update_table_signal.emit([])  # 清空表格
                self.update_button_signal.emit(True, "解析", "btn_resolution")  # 恢复按钮状态
                return #这里的 return 语句表示从当前函数立即退出，不再执行后续代码。
            
            # 发送信号更新表格（在主线程中执行）
            self.update_table_signal.emit(video_items)
            
        except Exception as e:
            # 错误处理：在主线程显示错误消息
            error_msg = f"解析失败: {str(e)}"
            self.show_error_signal.emit("错误", error_msg)
            self.update_table_signal.emit([])  # 清空表格
            
        finally:
            # 使用信号更新按钮状态，恢复按钮状态（在主线程执行）
            self.update_button_signal.emit(True, "解析", "btn_resolution")
    
    @Slot(str, bool)
    def _update_login_dialog_ui(self, message, add_ok_button):
        """在主线程中更新登录对话框UI"""
        if hasattr(self, 'login_dialog') and self.login_dialog:
            self.login_dialog.setText(message)
            if add_ok_button:
                # 添加确认按钮
                self.login_dialog.setStandardButtons(QMessageBox.Ok)
                self.login_dialog.button(QMessageBox.Ok).setText("确定")




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
    def show_error_message(self, title, message):
        """显示错误消息对话框"""
        QMessageBox.critical(self.window, title, message)


    @Slot(bool, str, str)
    def update_button_state(self, enabled, text, button_id="btn_resolution"):
        """更新按钮状态，默认为解析按钮"""
        if button_id == "btn_resolution":
            self.btn_resolution.setEnabled(enabled)
            self.btn_resolution.setText(text)
        elif button_id == "btn_favorites":
            self.btn_favorites.setEnabled(enabled)
            self.btn_favorites.setText(text)
        elif button_id == "btn_likes":
            self.btn_likes.setEnabled(enabled)
            self.btn_likes.setText(text)
        elif button_id == "btn_download":
            self.btn_download.setEnabled(enabled)
            self.btn_download.setText(text)

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
        self._set_ui_enabled(False)
        
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
        
        # 弹窗布局设置：垂直布局
        layout = QVBoxLayout(self.download_dialog)
        
        # 进度标签
        self.download_progress_label = QLabel("正在准备下载...", self.download_dialog)
        # 使用setAlignment(Qt.AlignCenter)使文本居中显示
        self.download_progress_label.setAlignment(Qt.AlignCenter)
        # 将标签添加到布局中才能显示
        layout.addWidget(self.download_progress_label)
        
        # 进度条,创建了一个QProgressBar进度条对象
        self.progress_bar = QProgressBar(self.download_dialog)
        # 设置进度条的范围，从0到总视频数量
        self.progress_bar.setRange(0, len(self.video_items))
        # 初始化进度条值为0
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # 取消按钮,创建了一个QPushButton按钮对象，并连接了点击事件
        self.download_cancel_button = QPushButton("取消下载", self.download_dialog)
        # 将按钮点击信号与_cancel_download槽函数连接
        self.download_cancel_button.clicked.connect(self._cancel_download)
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
            
        self._set_ui_enabled(True)
        self.btn_download.setEnabled(True)
        self.btn_download.setText("下载")
        
        QMessageBox.information(self.window, "下载取消", "下载操作已取消")

    def _set_ui_enabled(self, enabled):
        """设置UI控件的可用状态"""
        self.btn_resolution.setEnabled(enabled)
        self.btn_favorites.setEnabled(enabled)
        self.btn_likes.setEnabled(enabled)
        self.btn_select_file.setEnabled(enabled)
        self.url_input.setEnabled(enabled)
        self.table_widget.setEnabled(enabled)




    @Slot(int)  # 添加参数类型
    def download_completed(self, success_count):
        """下载完成处理"""
        if self.download_dialog:
            self.download_dialog.close()
            self.download_dialog = None
            
        self._set_ui_enabled(True)
        self.btn_download.setEnabled(True)
        self.btn_download.setText("下载")
        
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
            
        self._set_ui_enabled(True)
        self.btn_download.setEnabled(True)
        self.btn_download.setText("下载")
        
        QMessageBox.critical(self.window, "下载错误", f"下载失败: {error_msg}")
        
        # 这里不应再显示"下载完成"的消息
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