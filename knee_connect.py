import sys
from vision_thread import CameraThread
from voice_thread import SpeechThread

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QTextEdit, QFrame, 
                             QSpacerItem, QSizePolicy, QInputDialog, QStyle)
from PyQt6.QtCore import Qt, pyqtSlot, QUrl
from PyQt6.QtGui import QImage, QPixmap

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dialog - KneeConnect.ui")
        self.setGeometry(100, 100, 1000, 600)

        # Main layout container
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top Section: Split View (Camera | Instructions)
        top_layout = QHBoxLayout()
        
        # --- Camera Section ---
        self.camera_frame = QFrame()
        self.camera_frame.setStyleSheet("border: 1px solid black; background-color: #000;")
        self.camera_frame.setMinimumSize(480, 480)
        
        # We use a layout inside the frame to stack the feed and the overlay buttons
        self.camera_layout = QVBoxLayout(self.camera_frame)
        self.camera_layout.setContentsMargins(0, 0, 0, 0)
        
        # Overlay Buttons Container (Top Right of Camera Frame)
        # Using a specialized layout or just adding them to the top of the VBox
        camera_controls_layout = QHBoxLayout()
        camera_controls_layout.addStretch()
        

        self.btn_cam_reset = QPushButton("Reset")           # Placeholder for icon
        
        # Styling for overlay buttons to look small and unobtrusive
        # Styling for overlay buttons to look small and unobtrusive
        for btn in [self.btn_cam_reset]:
            btn.setFixedSize(60, 25)
            btn.setStyleSheet("background-color: rgba(255, 255, 255, 0.7); border: none; border-radius: 3px;")
            camera_controls_layout.addWidget(btn)
        
        self.camera_layout.addLayout(camera_controls_layout)
        
        # Camera Feed Label
        self.feed_label = QLabel("Camera Feed")
        self.feed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feed_label.setStyleSheet("color: white;")
        # Allow label to expand
        self.feed_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.camera_layout.addWidget(self.feed_label)
        
        top_layout.addWidget(self.camera_frame, stretch=1)
        
        # --- Instructions Section ---
        self.instructions_frame = QFrame(self)
        self.instructions_frame.setStyleSheet("border: 1px solid black; background-color: #e0e0e0;")
        self.instructions_frame.setMinimumSize(480, 480)
        
        instr_layout = QVBoxLayout(self.instructions_frame)
        instr_layout.setContentsMargins(0, 0, 0, 0)
        # instr_layout.setSpacing(0)
        
        # self.instr_label = QLabel("Instructions Video Placeholder")
        # self.instr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # instr_layout.addWidget(self.instr_label)
    ###------
        # Video widget
        self.video_widget = QVideoWidget(self.instructions_frame)
        instr_layout.addWidget(self.video_widget)
        
        # Media player
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
    ###------
        top_layout.addWidget(self.instructions_frame, stretch=1)
        
        main_layout.addLayout(top_layout, stretch=4)

        # Middle Section: Controls
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left: Select Exercise, Start, Stop
        self.btn_select_exercise = QPushButton("Select Exercise")
        self.btn_select_exercise.setMinimumHeight(50)
        self.btn_select_exercise.setMinimumWidth(150)
        self.style_primary_button(self.btn_select_exercise)
        
        # self.btn_start_pause = QPushButton("Start")
        # self.btn_start_pause.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        
        # self.btn_stop = QPushButton("Stop")
        # self.btn_stop.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        
        # self.control_buttons = [self.btn_start_pause, self.btn_stop]
        
        # Add primary button first
        controls_layout.addWidget(self.btn_select_exercise)
        
        # # Add control buttons next to it
        # for btn in self.control_buttons:
        #     btn.setMinimumHeight(40)
        #     btn.setMinimumWidth(100)
        #     self.style_secondary_button(btn)
        #     btn.setEnabled(False) # Disabled initially
        #     controls_layout.addWidget(btn)

        controls_layout.addStretch() 
        
        # Right: Secondary Buttons
        self.btn_show_progress = QPushButton("Show Progress")
        self.btn_patient_info = QPushButton("Patient Info")
        
        for btn in [self.btn_show_progress, self.btn_patient_info]:
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(120)
            self.style_secondary_button(btn)
            controls_layout.addWidget(btn)
            
        main_layout.addLayout(controls_layout)
        
        # Connect buttons
        self.btn_select_exercise.clicked.connect(self.select_exercise)
        # self.btn_start_pause.clicked.connect(self.toggle_start_pause)

        # self.btn_stop.clicked.connect(self.stop_process)
        self.btn_cam_reset.clicked.connect(self.toggle_camera_power)

        self.btn_show_progress.clicked.connect(lambda: print("Show Progress clicked"))
        self.btn_patient_info.clicked.connect(lambda: print("Patient Info clicked"))

        self.thread_1 = None
        self.is_running = False # Capture running state
        self.is_paused = False  # Processing paused state
        self.camera_on = True   # Camera power state

        # Auto-start camera thread for feed (but processing depends on Start)
        self.start_camera_thread()

    def style_primary_button(self, btn):
        btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50; 
                color: white; 
                border-radius: 10px;
                font-size: 14px; 
                font-weight: bold;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:pressed { background-color: #3e8e41; }
        """)

    def style_secondary_button(self, btn):
        btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0; 
                color: black; 
                border: 1px solid #ccc;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #e0e0e0; }
            QPushButton:disabled { background-color: #ddd; color: #999; }
        """)
#-------------------------------------------------------------------------------------------------#
    
    def select_exercise(self):
        # Simulate opening a list of exercises
        items = ("Squats", "Seated Knee Bending", "Straight Leg Raises")
        item, ok = QInputDialog.getItem(self, "Select Exercise", 
                                        "Choose an exercise:", items, 0, False)
        if ok and item:
            print(f"Exercise selected: {item}")
            # Enable buttons
            # for btn in self.control_buttons:
            #     btn.setEnabled(True)
            if item == "Squats":
                self.play_instruction_video("../videos/squats.mp4")
                self.thread_1.item = "Squats"
                # self.start_speech_thread()
                self.start_main_process()
            elif item == "Seated Knee Bending":
                self.play_instruction_video("../videos/Seated_Knee_Bending.mp4")
                self.thread_1.item = "Seated Knee Bending"
                # self.start_speech_thread()
                self.start_main_process()
            elif item == "Straight Leg Raises":
                self.play_instruction_video("../videos/Straight_Leg_Raises.mp4")
                self.thread_1.item = "Straight Leg Raises"
                # self.start_speech_thread()
                self.start_main_process()
    
    def play_instruction_video(self, video_path):
        self.media_player.setSource(QUrl.fromLocalFile(video_path))
        self.media_player.play()
    
    def start_camera_thread(self):
        if not self.thread_1:
            self.thread_1 = CameraThread()
            self.thread_1.change_pixmap_signal.connect(self.update_image)
            self.thread_1.start()

    def stop_camera_thread(self):
        if self.thread_1:
            self.thread_1.stop()
            self.thread_1 = None

    def start_main_process(self):
        self.is_running = True
        self.thread_1.process_enabled = True
        self.is_paused = False
        # self.btn_start_pause.setText("Pause")
        # self.btn_start_pause.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        print("Main process started (camera processing ON)")

    def toggle_camera_power(self):
        self.camera_on = not self.camera_on
        if self.camera_on:
            self.start_camera_thread()
            # self.btn_cam_off.setText("Off")
        else:
            self.stop_camera_thread()
            self.feed_label.clear()
            self.feed_label.setText("Camera Off")
            # self.btn_cam_off.setText("On")
    
    # def start_speech_thread(self):
    #     self.thread_2 = SpeechThread()
    #     self.thread_2.recognized.connect(self.handle_recognized_text)
    #     self.thread_2.start()

    # def start_speech_thread(self):
    #     self.thread_2 = SpeechThread()
    #     self.thread_2.result.connect(self.handle_voice_command)
    #     self.thread_2.start()

    # def handle_voice_command(self, text):
    #     print("User said:", text)
    
    #     if "yes" in text or "ready" in text:
    #         self.start_main_process()
    
        # elif "no" in text and "repeat" in text:
        #     self.start_speech_thread()  # repeat assistant
    
        # else:
        #     self.start_speech_thread()  # unclear → repeat

    # def toggle_start_pause(self):
    #     if not self.is_running:
    #         # First start
    #         self.is_running = True
    #         self.is_paused = False
    #         self.btn_start_pause.setText("Pause")
    #         self.btn_start_pause.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
    #         print("Process Started")
    #     else:
    #         # Toggle Pause/Resume
    #         is_paused = not self.is_paused
    #         self.is_paused = is_paused
    #         self.btn_start_pause.setText("Start" if is_paused else "Pause")
    #         icon = QStyle.StandardPixmap.SP_MediaPlay if is_paused else QStyle.StandardPixmap.SP_MediaPause
    #         self.btn_start_pause.setIcon(self.style().standardIcon(icon))
    #         print(f"Process {'Paused' if is_paused else 'Resumed'}")

    # def stop_process(self):
    #     self.is_running = False
    #     self.is_paused = False
    #     self.btn_start_pause.setText("Start")
    #     self.btn_start_pause.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
    #     # Disable buttons again? Or keep them enabled allowing restart?
    #     # Usually checking 'Stop' resets the session.
    #     print("Process Stopped")

    @pyqtSlot(QImage)
    def update_image(self, qt_img):
        if self.camera_on:
            # Scale to fit label while maintaining aspect ratio
            scaled_pixmap = QPixmap.fromImage(qt_img).scaled(
                self.feed_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.feed_label.setPixmap(scaled_pixmap)

    # def handle_recognized_text(self, text):
    #     print("Assistant heard:", text)

    # def closeEvent(self, event):
    #     self.stop_camera_thread()
    #     event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())