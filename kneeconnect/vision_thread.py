# vision_thread.py
# Uses MediaPipe "Solutions" (works with mediapipe==0.10.14)

import time
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
    # emits status messages (e.g. "Camera opened", "Camera failed")
    camera_status_signal = pyqtSignal(str)
    # emits (left_correct, left_total, right_correct, right_total) for Straight Leg Raises
    side_reps_signal = pyqtSignal(int, int, int, int)

    def __init__(self):
        super().__init__()
        self._run_flag = True

        # Controlled by GUI
        self.process_enabled = False
        self.item = ""  # "Squats" / "Seated Knee Bending" / "Straight Leg Raises"
        self.target_leg = "auto"  # "auto" / "right" / "left"

        # Stats
        self.reps = 0
        self.total_reps = 0
        self.knee_angle = 0
        self.hip_angle = 0
        self.color = (255, 255, 0)

        # Exercise logic
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

        # Video path (used when use_webcam is False)
        self.video_path = r"C:\Users\Mahsa\Downloads\knee_connect-main\knee_connect-main\videos\Seated_Knee_Bending.mp4"
        self.use_webcam = False

        # Countdown state machine
        # "idle"    = no countdown, normal tracking
        # "waiting" = waiting for hand wave gesture
        # "counting"= showing 3, 2, 1
        # "go"      = showing GO! briefly
        self.countdown_state = "idle"
        self._countdown_start = 0.0
        self._countdown_last_num = 0
        self._go_start = 0.0

        # Hand gesture detection
        self._wrist_history = []
        self._WAVE_WINDOW = 45         # frames to keep
        self._WAVE_DIR_CHANGES = 2     # direction changes needed (lowered)

    def reset_exercise(self):
        """Reset all exercise counters and state for a fresh start."""
        self.reps = 0
        self.total_reps = 0
        self.knee_angle = 0
        self.hip_angle = 0
        self.color = (255, 255, 0)
        self.squat_counter = Squat()
        self.knee_bend = SeatedKneeBend()
        self.leg_raise = StraightLegRaise()
        self._wrist_history = []
        self._hand_raised_since = 0.0
        print(f"Exercise reset for: {self.item}")
        self._hand_raised_since = 0.0  # fallback: hand held up for 2s
        self._HAND_HOLD_SECS = 2.0

    def detect_wave(self, lm):
        """Detect hand wave OR hand held above head for 2 seconds."""
        mp_pose = mp.solutions.pose.PoseLandmark

        # Check both wrists — use whichever is higher
        r_wrist = lm[mp_pose.RIGHT_WRIST]
        l_wrist = lm[mp_pose.LEFT_WRIST]
        r_shoulder = lm[mp_pose.RIGHT_SHOULDER]
        l_shoulder = lm[mp_pose.LEFT_SHOULDER]
        nose = lm[mp_pose.NOSE]

        # Pick the wrist that is raised above its shoulder
        wrist = None
        if r_wrist.y < r_shoulder.y:
            wrist = r_wrist
        elif l_wrist.y < l_shoulder.y:
            wrist = l_wrist

        if wrist is None:
            self._wrist_history.clear()
            self._hand_raised_since = 0.0
            return False

        now = time.time()

        # --- Fallback: hand held above head for 2 seconds ---
        hand_above_head = wrist.y < nose.y
        if hand_above_head:
            if self._hand_raised_since == 0.0:
                self._hand_raised_since = now
            elif now - self._hand_raised_since >= self._HAND_HOLD_SECS:
                self._hand_raised_since = 0.0
                self._wrist_history.clear()
                return True
        else:
            self._hand_raised_since = 0.0

        # --- Wave detection: horizontal oscillation ---
        self._wrist_history.append(wrist.x)
        if len(self._wrist_history) > self._WAVE_WINDOW:
            self._wrist_history.pop(0)

        if len(self._wrist_history) < 4:
            return False

        direction_changes = 0
        for i in range(2, len(self._wrist_history)):
            prev_diff = self._wrist_history[i - 1] - self._wrist_history[i - 2]
            curr_diff = self._wrist_history[i] - self._wrist_history[i - 1]
            if prev_diff * curr_diff < 0 and abs(curr_diff) > 0.003:
                direction_changes += 1

        if direction_changes >= self._WAVE_DIR_CHANGES:
            self._wrist_history.clear()
            self._hand_raised_since = 0.0
            return True

        return False

    def _draw_centered_text(self, frame, text, font_scale=4, thickness=8, color=(26, 188, 156)):
        """Draw large centered text on the frame."""
        h, w = frame.shape[:2]
        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[0]
        x = (w - text_size[0]) // 2
        y = (h + text_size[1]) // 2
        # Shadow
        cv2.putText(frame, text, (x + 3, y + 3),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
        # Main text
        cv2.putText(frame, text, (x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)

    def run(self):
        # --------- Open source ----------
        cap = None
        if self.use_webcam:
            # Try multiple backends and camera indices
            attempts = [
                (0, cv2.CAP_DSHOW, "webcam 0 (DSHOW)"),
                (0, cv2.CAP_MSMF, "webcam 0 (MSMF)"),
                (0, cv2.CAP_ANY, "webcam 0 (ANY)"),
                (1, cv2.CAP_DSHOW, "webcam 1 (DSHOW)"),
                (1, cv2.CAP_ANY, "webcam 1 (ANY)"),
            ]
            for idx, backend, desc in attempts:
                if not self._run_flag:
                    return
                print(f"Trying to open {desc}...")
                cap = cv2.VideoCapture(idx, backend)
                if cap.isOpened():
                    ret, test_frame = cap.read()
                    if ret and test_frame is not None:
                        print(f"Camera opened successfully: {desc}")
                        break
                    else:
                        cap.release()
                        cap = None
                else:
                    cap = None
        else:
            print("Trying to open video:", self.video_path)
            cap = cv2.VideoCapture(self.video_path)

        if cap is None or not cap.isOpened():
            print("ERROR: Could not open video/camera source.")
            self.camera_status_signal.emit("CAMERA FAILED: No camera found")
            return

        self.camera_status_signal.emit("Camera OK")
        loop_video = True

        while self._run_flag:
            ret, cv_img = cap.read()

            if not ret:
                if (not self.use_webcam) and loop_video:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break

            rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)

            # --------- Pose detection (when tracking is active) ----------
            results = None
            if self.process_enabled:
                rgb_image.flags.writeable = False
                results = self.pose.process(rgb_image)
                rgb_image.flags.writeable = True

            # --------- Exercise processing (landmarks + angles) ----------
            if self.process_enabled and results and results.pose_landmarks:
                try:
                    lm = results.pose_landmarks.landmark

                    if self.item == "Squats":
                        self.knee_angle, self.reps, self.color, _ = self.squat_counter.update(lm, rgb_image, self.target_leg)
                        self.total_reps = self.squat_counter.total_rep_count

                    elif self.item == "Seated Knee Bending":
                        self.knee_angle, self.reps, self.color, _ = self.knee_bend.update(lm, rgb_image, self.target_leg)
                        self.total_reps = self.knee_bend.total_rep_count

                    elif self.item == "Straight Leg Raises":
                        self.knee_angle, self.hip_angle, self.reps, self.color, _ = self.leg_raise.update(lm, rgb_image, self.target_leg)
                        self.total_reps = self.leg_raise.total_rep_count
                        self.side_reps_signal.emit(
                            self.leg_raise.left_rep_count,
                            self.leg_raise.left_total_rep_count,
                            self.leg_raise.right_rep_count,
                            self.leg_raise.right_total_rep_count,
                        )

                    else:
                        print(f"Unknown exercise: '{self.item}'")

                    self.stats_signal.emit(self.reps, self.total_reps, float(self.knee_angle), float(self.hip_angle))

                    # ── Side selection debug overlay ──────────────────────────
                    debug_str = get_side_debug_info(lm, self.target_leg)
                    h_dbg = rgb_image.shape[0]
                    cv2.putText(rgb_image, debug_str,
                                (10, h_dbg - 14),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                (220, 220, 0), 1, cv2.LINE_AA)
                except Exception as e:
                    print(f"Exercise processing error ({self.item}): {e}")
                    import traceback
                    traceback.print_exc()

            # --------- Countdown state machine (overlay) ----------
            if self.countdown_state == "waiting":
                # Auto-start: immediately begin countdown (no hand gesture required)
                self.countdown_state = "counting"
                self._countdown_start = time.time()
                self._countdown_last_num = 0

            elif self.countdown_state == "counting":
                elapsed = time.time() - self._countdown_start
                if elapsed < 1.0:
                    num = 3
                elif elapsed < 2.0:
                    num = 2
                elif elapsed < 3.0:
                    num = 1
                else:
                    self.countdown_state = "go"
                    self._go_start = time.time()
                    num = 0

                if num > 0:
                    if num != self._countdown_last_num:
                        self._countdown_last_num = num
                    self._draw_centered_text(rgb_image, str(num), 6, 12, (26, 188, 156))

            elif self.countdown_state == "go":
                elapsed = time.time() - self._go_start
                self._draw_centered_text(rgb_image, "GO!", 5, 10, (46, 204, 113))
                if elapsed > 0.8:
                    self.countdown_state = "idle"
                    self.process_enabled = True

            # --------- Overlay text ----------
            cv2.putText(rgb_image, f"Repetition: {self.reps}", (30, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, self.color, 3, cv2.LINE_AA)

            cv2.putText(rgb_image, f"Angle: {int(self.knee_angle)}", (30, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, self.color, 3, cv2.LINE_AA)

            # --------- Emit frame to PyQt ----------
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            img_copy = rgb_image.copy()
            qt_img = QImage(img_copy.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            self.change_pixmap_signal.emit(qt_img.copy())

        cap.release()

    def stop(self):
        self._run_flag = False
        if not self.wait(5000):
            self.terminate()
            self.wait()
