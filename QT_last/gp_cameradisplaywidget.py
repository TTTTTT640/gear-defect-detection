import cv2
from PyQt5.QtWidgets import QLabel                             
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt, QMutex,QThread,pyqtSignal, QWaitCondition


import gp_globals
class CameraQThread(QThread):
    """使用QThread的摄像头线程"""
    frame_ready = pyqtSignal(object)  # 发送帧信号
    error_occurred = pyqtSignal(str)
    
    def __init__(self, camera_id):
        super().__init__()
        self.camera_id = camera_id
        self.running = True
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        
    def run(self):
        """QThread的run方法"""
        cap = cv2.VideoCapture(self.camera_id, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        
        if not cap.isOpened():
            self.error_occurred.emit(f"无法打开摄像头 {self.camera_id}")
            return
        
        while self.running:
            ret, frame = cap.read()
            if ret:
                # 通过信号发送帧，避免锁竞争
                self.frame_ready.emit(frame.copy())
            else:
                self.msleep(10)  # 避免空转
        
        cap.release()
    
    def stop(self):
        """停止线程"""
        self.running = False
        self.wait()  # 等待线程结束

class CameraDisplayWidget(QLabel):
    """用于显示摄像头画面的自定义控件（只显示原始画面）"""
    def __init__(self, camera_index=3, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        #self.cap = None
        
        #self.setMinimumSize(320, 240)
        #self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        #self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

        self.setFixedSize(320, 240)    # 或者直接固定
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("border: 2px solid #cccccc; background-color: #f0f0f0;")
        
    def start_camera(self):
        """启动摄像头"""
        print(f"start_camera{self.camera_index}")
        


        try:
            # 使用QThread
            self.camera_thread = CameraQThread(self.camera_index)
            
            # 连接信号
            self.camera_thread.frame_ready.connect(self.on_frame_received)
            self.camera_thread.error_occurred.connect(self.on_error)
            
            # 启动线程
            self.camera_thread.start()
            
            print(f"摄像头 {self.camera_index} 启动成功")
            return True
        except Exception as e:
            print(f"摄像头启动错误: {e}")
            self.setText(f"错误: {str(e)}")
            return False
    def on_frame_received(self, frame):
        """接收帧信号（在主线程中执行）"""
        self.current_frame = frame
        self.update_display()

    def update_display(self):
        """更新显示（在主线程中执行）"""
        if self.current_frame is not None:
            rgb = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(img).scaled(
                320, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.setPixmap(pixmap)   
            with gp_globals.frame_lock:
                gp_globals.frame = self.current_frame.copy()
    #def update_frame2(self):
       # if self.t2.frame is not None:
          #  rgb = cv2.cvtColor(self.t2.frame, cv2.COLOR_BGR2RGB)
          #  h, w, ch = rgb.shape
          #  img = QImage(rgb.data, w, h, ch*w, QImage.Format_RGB888)
          #  self.setPixmap(QPixmap.fromImage(img).scaled(
          #  self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))           
                
    
    

      #  self.t2.join()
    def on_error(self, error_msg):
        """错误处理"""
        print(f"摄像头错误: {error_msg}")
        self.setText(f"错误: {error_msg}")
    
    def stop_camera(self):
        """停止摄像头"""
        if self.camera_thread:
            self.camera_thread.stop()
            self.camera_thread = None
            self.setText(f"摄像头 {self.camera_index} 已停止")