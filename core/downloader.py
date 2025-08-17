import requests
from PySide6.QtCore import QThread, Signal
import os


class Downloader(QThread):
    """视频下载线程类"""
    progress = Signal(int, int, bool)  # 当前序号, 总数, 是否成功
    finished = Signal(int)  # 参数为成功下载的数量
    error = Signal(str) # 参数为错误信息

    def __init__(self, video_items, save_path):
        super().__init__()
        self.video_items = video_items
        self.save_path = save_path
        self.cancel_flag = False

    def run(self):
        """执行下载任务"""
        success_count = 0
        total = len(self.video_items)
        # failed_items = []
        
        for i,video in enumerate(self.video_items):
            if self.cancel_flag:
                break
            try:
                # 更新进度 - 开始下载
                self.progress.emit(i, total, False)
                
                # 下载逻辑
                url = video.url
                file_path = os.path.join(self.save_path, f"{video.title}.mp4")

                # 检查文件是否已存在,已存在则跳过下载
                if os.path.exists(file_path):
                    success_count += 1
                    self.progress.emit(i + 1, total, True)
                    continue

                
                # 下载视频内容
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Referer': 'https://www.douyin.com/',
                    'Accept': '*/*',
                    'Connection': 'keep-alive'
                }

                # 创建临时文件路径
                response = requests.get(url, stream=True, headers=headers)
                response.raise_for_status()
                
                # 写入文件
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                success_count += 1
                
                # 更新进度 - 成功
                self.progress.emit(i+1, total, True)
                
            except Exception as e:
                # 更新进度 - 失败
                self.progress.emit(i+1, total, False)
                # 可以选择记录错误日志
                
        self.finished.emit(success_count)

    def cancel(self):
        """取消下载"""
        self.cancel_flag = True
    

            