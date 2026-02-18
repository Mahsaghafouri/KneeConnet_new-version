import cv2
import numpy as np
import mediapipe as mp

def calculate_angle(a, b, c):
    
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    
    ba = a - b
    bc = c - b
    
    denom = (np.linalg.norm(ba) * np.linalg.norm(bc)) + 1e-8
    cosine_angle = np.dot(ba, bc) / denom
    cosine_angle = np.clip(cosine_angle, -1.0, 1.0)
    angle = np.degrees(np.arccos(cosine_angle))
    
    return angle

def draw_landmark(frame, lm, color, r=7):
    h, w, _ = frame.shape
    cv2.circle(frame, (int(lm.x*w), int(lm.y*h)), r, color, -1)

def draw_line(frame, lm1, lm2, color, t=4):
    h, w, _ = frame.shape
    p1 = (int(lm1.x*w), int(lm1.y*h))
    p2 = (int(lm2.x*w), int(lm2.y*h))
    cv2.line(frame, p1, p2, color, t)

def draw_warning(frame, text, y):
    cv2.putText(frame, text, (30, y),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3)

def is_right_side_visible(lm, threshold=0.08):
    r = lm[mp.solutions.pose.PoseLandmark.RIGHT_HIP]
    l = lm[mp.solutions.pose.PoseLandmark.LEFT_HIP]
    return abs(r.x - l.x) < threshold

class Squat:
    NEUTRAL = "NEUTRAL"
    GOOD = "GOOD"
    BAD = "BAD"

    STATE_COLORS = {
        NEUTRAL: (255, 255, 0),   # Yellow
        GOOD: (0, 255, 0),        # Green
        BAD: (255, 0, 0)          # Red
    }

    def __init__(self):
        self.last_state = "UP"
        self.rep_count = 0
        self.total_rep_count = 0

        self.KNEE_MIN = 90            # too deep below this
        self.KNEE_MAX = 160
        self.TORSO_MAX = 40           # degrees
        self.HEEL_THRESH = 0.01
        self.KNEE_FWD_THRESH = 0.02

    def torso_lean_excessive(self, lm, frame):
        h, w, _ = frame.shape
        hip = lm[mp.solutions.pose.PoseLandmark.RIGHT_HIP]
        sh = lm[mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER]

        hip_pt = np.array([hip.x*w, hip.y*h])
        sh_pt = np.array([sh.x*w, sh.y*h])

        v = sh_pt - hip_pt
        angle = abs(np.degrees(np.arctan2(v[0], -v[1])))

        return angle > self.TORSO_MAX

    def heels_lifted(self, lm):
        foot = lm[mp.solutions.pose.PoseLandmark.RIGHT_FOOT_INDEX]
        heel = lm[mp.solutions.pose.PoseLandmark.RIGHT_HEEL]
        return (foot.y - heel.y) > self.HEEL_THRESH

    def knee_too_far_forward(self, lm):
        knee = lm[mp.solutions.pose.PoseLandmark.RIGHT_KNEE]
        foot = lm[mp.solutions.pose.PoseLandmark.RIGHT_FOOT_INDEX]
        return (knee.x - foot.x) > self.KNEE_FWD_THRESH

    def evaluate_form(self, knee_angle, lean_bad, heels_bad, knee_fwd_bad):
        errors = {
            "knee_depth": knee_angle < self.KNEE_MIN or knee_angle > self.KNEE_MAX,
            "torso": lean_bad,
            "heels": heels_bad,
            "knee_forward": knee_fwd_bad
        }

        if any(errors.values()):
            return self.BAD, errors
        return self.GOOD, errors

    def update(self, lm, frame):

        side_ok = is_right_side_visible(lm)

        lean_bad = self.torso_lean_excessive(lm, frame)
        heels_bad = self.heels_lifted(lm)
        knee_fwd_bad = self.knee_too_far_forward(lm)

        sh_lm = lm[mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER]
        
        hip_lm = lm[mp.solutions.pose.PoseLandmark.RIGHT_HIP]
        knee_lm = lm[mp.solutions.pose.PoseLandmark.RIGHT_KNEE]
        ankle_lm = lm[mp.solutions.pose.PoseLandmark.RIGHT_ANKLE]

        hip = [hip_lm.x, hip_lm.y]
        knee = [knee_lm.x, knee_lm.y]
        ankle = [ankle_lm.x, ankle_lm.y]

        knee_angle = calculate_angle(hip, knee, ankle)

        foot_lm = lm[mp.solutions.pose.PoseLandmark.RIGHT_FOOT_INDEX]
        heel_lm = lm[mp.solutions.pose.PoseLandmark.RIGHT_HEEL]

        if knee_angle < 120:
            motion = "DOWN"
        elif knee_angle > 160:
            motion = "UP"
        else:
            motion = self.last_state

        visual_state = self.NEUTRAL
        errors = {}

        if side_ok and motion == "DOWN":
            if self.last_state == "UP":
                self.total_rep_count += 1
            visual_state, errors = self.evaluate_form(
                knee_angle, lean_bad, heels_bad, knee_fwd_bad)

            if visual_state == self.GOOD and self.last_state == "UP":
                self.rep_count += 1

        color = self.STATE_COLORS[visual_state]

        if not side_ok:
            draw_warning(frame, "TURN SIDEWAYS", 120)

        if visual_state == self.BAD:
            y = 140
            if errors["knee_depth"]:
                draw_warning(frame, "Incorrect squat depth", y); y += 40
            if errors["torso"]:
                draw_warning(frame, "Excessive torso lean", y); y += 40
            if errors["heels"]:
                draw_warning(frame, "Heels lifted", y); y += 40
            if errors["knee_forward"]:
                draw_warning(frame, "Knee past toes", y)

        draw_landmark(frame, sh_lm, color)
        draw_line(frame, hip_lm, sh_lm, color)
            
        draw_landmark(frame, hip_lm, color)
        draw_landmark(frame, knee_lm, color)
        draw_landmark(frame, ankle_lm, color)
        draw_line(frame, hip_lm, knee_lm, color)
        draw_line(frame, knee_lm, ankle_lm, color)

        draw_landmark(frame, foot_lm, color)
        draw_landmark(frame, heel_lm, color)
        draw_line(frame, foot_lm, heel_lm, color)

        self.last_state = motion

        return knee_angle, self.rep_count, color


class SeatedKneeBend:
    NEUTRAL = "NEUTRAL"
    GOOD = "GOOD"
    BAD = "BAD"

    STATE_COLORS = {
        NEUTRAL: (255, 255, 0),   # Yellow
        GOOD: (0, 255, 0),        # Green
        BAD: (255, 0, 0)          # Red
    }
    
    def __init__(self):
        self.last_state = "EXTENDED"
        self.rep_count = 0
        self.total_rep_count = 0

        self.hip_ref_y = None

        self.KNEE_MIN = 105            # too deep below this
        self.KNEE_MAX = 150
        self.TORSO_MAX = 30           # degrees
        self.HIP_LIFT_THRESH = 0.02

    def torso_lean_excessive(self, lm, frame):
        h, w, _ = frame.shape
        hip = lm[mp.solutions.pose.PoseLandmark.RIGHT_HIP]
        sh = lm[mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER]

        hip_pt = np.array([hip.x*w, hip.y*h])
        sh_pt = np.array([sh.x*w, sh.y*h])

        v = sh_pt - hip_pt
        angle = abs(np.degrees(np.arctan2(v[0], -v[1])))

        return angle > self.TORSO_MAX

    def hip_lifted(self, lm):
        hip = lm[mp.solutions.pose.PoseLandmark.RIGHT_HIP]
        if self.hip_ref_y is None:
            return False
        # print(hip.y)
        return abs(hip.y - self.hip_ref_y) > self.HIP_LIFT_THRESH
        
    def evaluate_form(self, lean_bad, hip_bad):
        errors = {
            "torso": lean_bad,
            "hip": hip_bad,
        }

        if any(errors.values()):
            return self.BAD, errors
        return self.GOOD, errors
        
    def update(self, lm, frame):

        side_ok = is_right_side_visible(lm)
        
        sh_lm = lm[mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER]
        hip_lm = lm[mp.solutions.pose.PoseLandmark.RIGHT_HIP]
        knee_lm = lm[mp.solutions.pose.PoseLandmark.RIGHT_KNEE]
        ankle_lm = lm[mp.solutions.pose.PoseLandmark.RIGHT_ANKLE]

        hip = [hip_lm.x, hip_lm.y]
        knee = [knee_lm.x, knee_lm.y]
        ankle = [ankle_lm.x, ankle_lm.y]

        knee_angle = calculate_angle(hip, knee, ankle)

        if knee_angle < self.KNEE_MIN:
            motion = "BENT"
        elif knee_angle > self.KNEE_MAX:
            motion = "EXTENDED"
        else:
            motion = self.last_state

        if motion == "BENT" and self.hip_ref_y is None:
            self.hip_ref_y = hip_lm.y

        lean_bad = self.torso_lean_excessive(lm, frame)
        hip_bad = self.hip_lifted(lm)
        
        visual_state = self.NEUTRAL
        errors = {}
            
        if side_ok and motion == "BENT":
            if self.last_state == "EXTENDED":
                self.total_rep_count += 1
            visual_state, errors = self.evaluate_form(
                lean_bad, hip_bad)

            if visual_state == self.GOOD and self.last_state == "EXTENDED":
                self.rep_count += 1

        color = self.STATE_COLORS[visual_state]
        
        if not side_ok:
            draw_warning(frame, "TURN SIDEWAYS", 120)

        if visual_state == self.BAD:
            y = 160
            if errors["torso"]:
                draw_warning(frame, "Do not lean backward", y); y += 40
            if errors["hip"]:
                draw_warning(frame, "Keep your hip on the chair", y)

        draw_landmark(frame, sh_lm, color)
        draw_line(frame, hip_lm, sh_lm, color)

        draw_landmark(frame, hip_lm, color)
        draw_landmark(frame, knee_lm, color)
        draw_landmark(frame, ankle_lm, color)

        draw_line(frame, hip_lm, knee_lm, color)
        draw_line(frame, knee_lm, ankle_lm, color)

        self.last_state = motion
            
        return knee_angle, self.rep_count, color

class StraightLegRaise:
    NEUTRAL = "NEUTRAL"
    GOOD = "GOOD"
    BAD = "BAD"

    STATE_COLORS = {
        NEUTRAL: (255, 255, 0),
        GOOD: (0, 255, 0),
        BAD: (255, 0, 0)
    }
    
    def __init__(self):
        self.last_state = "DOWN"
        self.rep_count = 0
        self.total_rep_count = 0

        self.KNEE_STRAIGHT = 160
        self.HIP_RAISE_MIN = 140     # degrees
        self.TORSO_MAX = 20

    def torso_lifted(self, lm, frame):
        h, w, _ = frame.shape
        hip = lm[mp.solutions.pose.PoseLandmark.RIGHT_HIP]
        sh = lm[mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER]

        hip_pt = np.array([hip.x * w, hip.y * h])
        sh_pt = np.array([sh.x * w, sh.y * h])

        v = sh_pt - hip_pt
        angle = abs(np.degrees(np.arctan2(-v[1], v[0])))
        return 180 - angle > self.TORSO_MAX

    def evaluate_form(self, knee_bad, hip_bad, torso_bad):
        errors = {
            "knee": knee_bad,
            "hip": hip_bad,
            "torso": torso_bad
        }

        if any(errors.values()):
            return self.BAD, errors
        return self.GOOD, errors

    def update(self, lm, frame):

        side_ok = is_right_side_visible(lm)
        
        sh_lm = lm[mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER]
        hip_lm = lm[mp.solutions.pose.PoseLandmark.RIGHT_HIP]
        knee_lm = lm[mp.solutions.pose.PoseLandmark.RIGHT_KNEE]
        ankle_lm = lm[mp.solutions.pose.PoseLandmark.RIGHT_ANKLE]

        shoulder = [sh_lm.x, sh_lm.y]
        hip = [hip_lm.x, hip_lm.y]
        knee = [knee_lm.x, knee_lm.y]
        ankle = [ankle_lm.x, ankle_lm.y]

        knee_angle = calculate_angle(hip, knee, ankle)
        hip_angle = calculate_angle(shoulder, hip, knee)
        # print(hip_angle)

        if hip_angle > self.HIP_RAISE_MIN:
            motion = "UP"
        else:
            motion = "DOWN"

        knee_bad = knee_angle < self.KNEE_STRAIGHT
        hip_bad = hip_angle < self.HIP_RAISE_MIN
        torso_bad = self.torso_lifted(lm, frame)

        visual_state = self.NEUTRAL
        errors = {}

        if side_ok and motion == "UP":
            if self.last_state == "DOWN":
                self.total_rep_count += 1
            visual_state, errors = self.evaluate_form(
                knee_bad, hip_bad, torso_bad
            )

            if visual_state == self.GOOD and self.last_state == "DOWN":
                self.rep_count += 1
                
        color = self.STATE_COLORS[visual_state]
        
        if not side_ok:
            draw_warning(frame, "TURN SIDEWAYS", 120)

        if visual_state == self.BAD:
            y = 160
            if errors["knee"]:
                draw_warning(frame, "Keep knee straight", y); y += 40
            if errors["hip"]:
                draw_warning(frame, "Raise leg higher", y); y += 40
            if errors["torso"]:
                draw_warning(frame, "Do not lift trunk", y)

        draw_landmark(frame, sh_lm, color)
        draw_line(frame, hip_lm, sh_lm, color)

        draw_landmark(frame, hip_lm, color)
        draw_landmark(frame, knee_lm, color)
        draw_landmark(frame, ankle_lm, color)

        draw_line(frame, hip_lm, knee_lm, color)
        draw_line(frame, knee_lm, ankle_lm, color)

        self.last_state = motion

        return knee_angle, hip_angle, self.rep_count, color    
