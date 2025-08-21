from DrissionPage import ChromiumPage,ChromiumOptions,SessionPage
import re
import traceback
from .models import VideoItem
import time 

'''爬虫主程序，负责解析URL地址中包含的视频信息，包括视频标题、视频地址等
    方法列表：
        1.主方法
        2.解析输入链接，单个视频及主页所有视频
        3.解析我的收藏/喜欢
        4.滚动页面
        5.
    !!方法名前缀为下划线(_)，表明这是一个内部/私有方法，不建议从类外部直接调用
'''
class DouyinSpider:
    def __init__(self):
        self.page = None  # 浏览器页面实例
        self.browser = None  # 浏览器实例（如果需要单独访问）
        self.is_headless = False
        self.video_items = []
        self.cancel_flag = False  # 添加取消标志

    def check_cancel(self):
        """检查是否需要取消操作"""
        if self.cancel_flag:
            self.close_browser()
            raise InterruptedError("操作已取消")

    def create_browser(self, headless=False):           
        """创建浏览器实例，可复用已有实例，默认非无头模式"""
        # 如果已有浏览器且模式相同，直接返回
        if self.page and self.is_headless == headless:
            return self.page
        
        # 关闭旧浏览器（如果存在）
        if self.page:
            try:
                self.page.quit()
            except Exception as e:
                print(f"关闭浏览器出错: {e}")
        
        # 创建新浏览器
        co = ChromiumOptions()
        co.headless(headless)

        headers = {
            'referer':'https://www.douyin.com',
            'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'accept':'application/json, text/plain, */*',
            'accept-encoding':'gzip, deflate, br, zstd',
            'accept-language':'zh-CN,zh;q=0.9'
            
        }
        # 创建ChromiumPage对象
        self.check_cancel()
        self.page = ChromiumPage(co)
        self.page.set.headers(headers)
        self.is_headless = headless  # 记录当前模式
        return self.page # 每次创建都会覆盖原来的实例，除非模式相同

    
    def check_login_status(self):
        """检查登录状态（使用当前浏览器实例）"""
        if not self.page:
            raise RuntimeError("浏览器未初始化，请先调用 create_browser()")
        try:
            # 访问个人主页
            if 'douyin.com/' not in self.page.url:
                self.page.get('https://www.douyin.com/')
            
            # 检查是否存在登录元素
            login_elements = [
                'text=退出登录',
                'text:保存登录信息'
            ]
        
            for selector in login_elements:
                try:
                    if self.page.ele(selector, timeout=2):
                        print('检测为已登录')
                        return True
                except:
                    continue
            print("检测为未登录")
            return False
        except Exception as e:
            print(f"检查登录状态失败: {e}")
            return False

    def close_browser(self):
        """关闭浏览器"""
        if self.page:
            try:
                # ✅ 确保页面存在再尝试关闭
                if hasattr(self.page, 'quit'):
                    self.page.quit()
                self.page = None
                self.is_headless = False
            except Exception as e:
                print(f"关闭浏览器出错: {e}")

    def get_single_video(self, url):
        try:
            # 创建无头模式浏览器,调试时可以改成非无头模式查看效果
            self.create_browser(headless=False)
            self.page.listen.start('aweme/v1/web/aweme/detail/')            
            self.page.get(url)
            packets = self.page.listen.steps(timeout=10)
            MAX_TITLE_LENGTH = 200
            for idx, packet in enumerate(packets, 1):
                try:             
                    self.check_cancel()  # 添加取消检查
                    json_data = packet.response.body
                    # 注意：单个视频接口返回的是aweme_detail对象（非列表）,减少不必要的迭代（单个视频只需处理第一个有效数据包）
                    if 'aweme_detail' in json_data:
                        # video_info为字典
                        video_info = json_data['aweme_detail']
                        old_video_title = video_info.get('desc', '')
                        
                        # 清理非法字符作为文件名
                        video_title = re.sub(r'[\\/:*?"<>|!\n#]', '_', old_video_title)
                        # 截取标题长度，确保不超过Windows文件名限制
                        if len(video_title) > MAX_TITLE_LENGTH:
                            video_title = video_title[:MAX_TITLE_LENGTH]
                        # 获取最高清视频地址
                        url_list = video_info['video']['play_addr']['url_list']
                        # 生成器表达式：(url for url in url_list if 'v3-web.douyinvod.com' in url) 是一个生成器表达式，它会遍历url_list中的每个URL，
                        # next()函数：这个函数会从生成器中获取第一个满足条件的值
                        # 默认值：next()的第二个参数None表示如果没有找到满足条件的URL，则返回None
                        video_url = next((url for url in url_list if 'v3-web.douyinvod.com' in url), None)
                                           
                        # 如果没有找到v3-web.douyinvod.com的URL，打印错误信息
                        if not video_url:
                            print(f"⚠️ 未找到v3有效URL: {url_list}")

                        # 直接返回结果，不再继续处理后续包
                        return [VideoItem(url=video_url, title=video_title)]

                except Exception as e:
                    print(f"❌ 处理第 {idx} 个数据包失败: {str(e)}")
                    continue
            print("⚠️ 未找到有效视频数据包")
            return []
        except Exception as e:
            print(f"❌ 获取视频失败: {str(e)}")
            return []
        finally:
            self.close_browser()
            print('已关闭页面')
        
        
    def resolve_url(self, url):
        try:
            print(f"正在解析链接: {url}")            
            # 验证URL格式
            if not url or not url.startswith(('http://', 'https://')):
                print("URL格式无效")
                return None
                
            # 创建浏览器实例（如果还没有）
            if not hasattr(self, 'page') or not self.page:
                self.create_browser(headless=True)
       
            self.page.get(url)
            time.sleep(1)
            final_url = self.page.url
            print(f"解析后的链接: {final_url}")
            return final_url
        
        except Exception as e:
            print(f"解析URL时出错: {str(e)}")
            return None           
        
    def get_user_videos(self, url):
        try:
            # 创建无头模式浏览器
            self.create_browser(headless=False)        
            self.page.listen.start('aweme/v1/web/aweme/post/')
            self.page.get(url)
            self.check_cancel()  # 添加取消检查
            self._scroll_to_bottom()
            packets = self.page.listen.steps(timeout=10) #这里packets是生成器对象，listen.steps方法默认timeout=None，为None表示无限等待，此时的生成器是一个动态生成器，会持续阻塞等待新数据包，因此在后续的遍历中，会一直阻塞，导致后续逻辑无法执行，在这里需要手动设置timeout时间，来终止阻塞等待，timeout时间设置太短会导致数据包未获取完全，timeout时间设置太长会导致程序等待时间过长，因此需要根据实际情况来设置timeout时间
        
            # 遍历处理每个数据包
            video_items = self._process_video_packets(packets)
            return video_items
        except Exception as e:
            # print(f"获取个人视频失败: {e}")
            return []
        finally:
            self.close_browser()
    
    def get_favorites_videos(self):
        try:
            # 创建无头模式浏览器
            self.create_browser(headless=False)
            self.page.listen.start('aweme/v1/web/aweme/listcollection/')
            # 访问收藏页面
            self.page.get("https://www.douyin.com/user/self?showTab=favorite_collection")             
            self.check_cancel()  # 添加取消检查
            # 滚动到页面底部加载所有收藏视频
            self._scroll_to_bottom()
            packets = self.page.listen.steps(timeout=10) #这里packets是生成器对象，listen.steps方法默认timeout=None，为None表示无限等待，此时的生成器是一个动态生成器，会持续阻塞等待新数据包，因此在后续的遍历中，会一直阻塞，导致后续逻辑无法执行，在这里需要手动设置timeout时间，来终止阻塞等待，timeout时间设置太短会导致数据包未获取完全，timeout时间设置太长会导致程序等待时间过长，因此需要根据实际情况来设置timeout时间
            
            # 遍历处理每个数据包
            video_items = self._process_video_packets(packets)
            return video_items
        except Exception as e:
            print(f"获取收藏视频失败: {e}")
            return []
        finally:
            self.close_browser()
        
    
    def get_likes_videos(self):
        try:
            # 创建无头模式浏览器
            self.create_browser(headless=True)
            # 使用auth_manager检查登录状态
            self.page.listen.start('aweme/v1/web/aweme/favorite/')
            # 访问喜欢页面
            self.page.get("https://www.douyin.com/user/self?showTab=like")
            self.check_cancel()  # 添加取消检查
            # 滚动到页面底部加载所有收藏视频
            self._scroll_to_bottom()
            packets = self.page.listen.steps(timeout=10) #这里packets是生成器对象，listen.steps方法默认timeout=None，为None表示无限等待，此时的生成器是一个动态生成器，会持续阻塞等待新数据包，因此在后续的遍历中，会一直阻塞，导致后续逻辑无法执行，在这里需要手动设置timeout时间，来终止阻塞等待，timeout时间设置太短会导致数据包未获取完全，timeout时间设置太长会导致程序等待时间过长，因此需要根据实际情况来设置timeout时间
        
            # 遍历处理每个数据包
            video_items = self._process_video_packets(packets)
            return video_items
        except Exception as e:
            print(f"获取喜欢视频失败: {e}")
            return []
        finally:
            self.close_browser()

    def _process_video_packets(self, packets):
        """处理视频数据包，提取视频信息"""
        video_items = []
        MAX_TITLE_LENGTH = 200  # Windows文件名最大长度限制，文件名过长会导致后续下载失败
        for idx, packet in enumerate(packets, 1):
            self.check_cancel()
            try:
                if not packet.response or not packet.response.body:
                    print(f"⚠️ 第 {idx} 个数据包无响应体")
                    continue
                json_data = packet.response.body
                aweme_list = json_data.get('aweme_list', [])
                
                if not aweme_list:
                    print(f"⚠️ 第 {idx} 个数据包无有效数据")
                    continue
                print(f"📦 处理第 {idx} 个数据包，包含 {len(aweme_list)} 个视频")    
                self.check_cancel()
                # 提取视频标题和链接并清洗
                for video_info in aweme_list:
                    old_video_title = video_info.get('desc', '')
                    # 如果 old_video_title 不为空，则执行替换操作；否则结果为空字符串
                    video_title = re.sub(r'[\\/:*?"<>|!\n#]', '_', old_video_title) if old_video_title else ''
                    # 截取标题长度，确保不超过Windows文件名限制
                    if len(video_title) > MAX_TITLE_LENGTH:
                        print(f"📏 标题过长({len(video_title)}字符)，已截断至{MAX_TITLE_LENGTH}字符")
                        video_title = video_title[:MAX_TITLE_LENGTH]
                    # 改进URL获取逻辑
                    url_list = video_info['video']['play_addr']['url_list']
                    video_url = None
                    
                    # 优先查找包含v3-web.douyinvod.com的URL
                    for url in url_list:
                        if 'v3-web.douyinvod.com' in url:
                            video_url = url
                            break
                    
                    # 如果没有找到v3-web.douyinvod.com的URL，打印错误信息
                    if not video_url:
                        print(f"⚠️ 第 {idx} 个数据包中的视频无v3有效URL")
                    
                    # 如果标题或URL为空，跳过该项
                    if not video_title or not video_url:
                        if not video_title:
                            print(f"⚠️ 第 {idx} 个数据包中的视频标题为空")
                        if not video_url:
                            print(f"⚠️ 第 {idx} 个数据包中的视频URL为空")
                        continue
                    video_item = VideoItem(url=video_url, title=video_title)
                    video_items.append(video_item)
            except Exception as e:
                print(f"❌ 处理第 {idx} 个数据包失败: {str(e)}")
                traceback.print_exc()
        
        print(f"✅ 成功提取 {len(video_items)} 个视频")
        return video_items

    def _scroll_to_bottom(self):
        """滚动加载所有视频列表内容"""
        # 记录滚动次数防止无限滚动
        scroll_count = 0
        max_scrolls = 50  # 最大滚动次数防止无限循环
        
        while scroll_count < max_scrolls:
            self.check_cancel()
            # 1. 检查是否已加载完成（存在结束元素）
            end_element = self.page.ele('text:没有更多了', timeout=1)
            if end_element:
                print("✅ 检测到结束元素，停止滚动")
                break
            
            # 2. 确保tab元素可见（触发加载）
            try:
                tab_element = self.page.ele('.user-page-footer', timeout=2)# 待验证：换一个不存在的元素，是否会执行滚动？
                if tab_element:
                # 滚动到元素位置（实现类似翻页效果）
                    self.page.scroll.to_see(tab_element)
                    print(f"🔄 滚动到页尾元素 ({scroll_count + 1}/{max_scrolls})")
                self.check_cancel()
                # 等待新内容加载
                time.sleep(1)  # 固定等待时间确保加载完成
            except:
            # 如果找不到页尾元素
                print("⚠️ 未找到页尾元素")           
            
            # 3. 增加滚动计数
            scroll_count += 1
            print(f"🔁 已滚动 {scroll_count} 次")
        
        # 检查退出原因
        if scroll_count >= max_scrolls:
            print(f"⚠️ 达到最大滚动次数 {max_scrolls}，停止滚动")
        else:
            print(f"✅ 成功加载所有内容，共滚动 {scroll_count} 次")       
        return scroll_count
    
