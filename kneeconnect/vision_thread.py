# vision_thread.py  (DROP-IN REPLACEMENT)
# Uses MediaPipe "Solutions" (works with mediapipe==0.10.14) and opens your video
# using the EXACT absolute path you provided.

import cv2
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage
import mediapipe as mp

from utils import *


class CameraThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)
    say_signal = pyqtSignal(str)
    # emits (correct_reps, total_reps, knee_angle, hip_angle) after each processed frame
    stats_signal = pyqtSignal(int, int, float, float)

    def __init__(self):
        super().__init__()
        self._run_flag = True

        # Controlled by GUI
        self.process_enabled = False
        self.item = ""  # "Squats" / "Seated Knee Bending" / "Straight Leg Raises"

        # Stats
        self.reps = 0
        self.total_reps = 0
        self.knee_angle = 0
        self.hip_angle = 0
        self.color = (255, 255, 0)

        # Exercise logic (your existing classes)
        self.squat_counter = Squat()
        self.knee_bend = SeatedKneeBend()
        self.leg_raise = StraightLegRaise()

        # MediaPipe Solutions (requires mediapipe==0.10.14)
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        # ✅ Your EXACT video path:
        self.video_path = r"C:\Users\Mahsa\Downloads\knee_connect-main\knee_connect-main\videos\Seated_Knee_Bending.mp4"

        # If you want WEBCAM instead, set this to True and ignore video_path
        self.use_webcam = False

    def run(self):
        # --------- Open source ----------
        if self.use_webcam:
            # On Windows, CAP_DSHOW helps OpenCV pick the camera backend
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            print("Trying to open webcam...")
        else:
            print("Trying to open video:", self.video_path)
            cap = cv2.VideoCapture(self.video_path)

        if not cap.isOpened():
            print("ERROR: Could not open video/camera source.")
            return

        # Optional: if video ends, restart from beginning (loop the video)
        loop_video = True

        while self._run_flag:
            ret, cv_img = cap.read()

            if not ret:
                # End of file or read error
                if (not self.use_webcam) and loop_video:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break

            rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)

            # --------- Pose processing ----------
            if self.process_enabled:
                rgb_image.flags.writeable = False
                results = self.pose.process(rgb_image)
                rgb_image.flags.writeable = True

                if results.pose_landmarks:
                    lm = results.pose_landmarks.landmark

                    if self.item == "Squats":
                        self.knee_angle, self.reps, self.color = self.squat_counter.update(lm, rgb_image)
                        self.total_reps = self.squat_counter.total_rep_count

                    elif self.item == "Seated Knee Bending":
                        self.knee_angle, self.reps, self.color = self.knee_bend.update(lm, rgb_image)
                        self.total_reps = self.knee_bend.total_rep_count

                    elif self.item == "Straight Leg Raises":
                        self.knee_angle, self.hip_angle, self.reps, self.color = self.leg_raise.update(lm, rgb_image)
                        self.total_reps = self.leg_raise.total_rep_count

                    self.stats_signal.emit(self.reps, self.total_reps, float(self.knee_angle), float(self.hip_angle))

            # --------- Overlay text ----------
            cv2.putText(rgb_image, f"Repetition: {self.reps}", (30, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, self.color, 3, cv2.LINE_AA)

            cv2.putText(rgb_image, f"Angle: {int(self.knee_angle)}", (30, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, self.color, 3, cv2.LINE_AA)

            # --------- Emit frame to PyQt ----------
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            p = qt_img.scaled(640, 480, Qt.AspectRatioMode.KeepAspectRatio)
            self.change_pixmap_signal.emit(p)

        cap.release()

    def stop(self):
        self._run_flag = False
        if not self.wait(5000):   # give thread 5 s to finish cleanly
            self.terminate()      # force-kill if still running
            self.wait()           # wait for termination to complete
