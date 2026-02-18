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

def _right_side():
    mp_pose = mp.solutions.pose.PoseLandmark
    return {
        "shoulder": mp_pose.RIGHT_SHOULDER,
        "hip": mp_pose.RIGHT_HIP,
        "knee": mp_pose.RIGHT_KNEE,
        "ankle": mp_pose.RIGHT_ANKLE,
        "foot_index": mp_pose.RIGHT_FOOT_INDEX,
        "heel": mp_pose.RIGHT_HEEL,
    }

def _left_side():
    mp_pose = mp.solutions.pose.PoseLandmark
    return {
        "shoulder": mp_pose.LEFT_SHOULDER,
        "hip": mp_pose.LEFT_HIP,
        "knee": mp_pose.LEFT_KNEE,
        "ankle": mp_pose.LEFT_ANKLE,
        "foot_index": mp_pose.LEFT_FOOT_INDEX,
        "heel": mp_pose.LEFT_HEEL,
    }

def get_visible_side(lm, preferred_side="auto"):
    if preferred_side == "right":
        return _right_side()
    elif preferred_side == "left":
        return _left_side()

    # Auto: prefer visibility scores; fall back to hip x-position
    mp_pose = mp.solutions.pose.PoseLandmark

    # Sum visibility of core landmarks for each side
    r_vis = (lm[mp_pose.RIGHT_HIP].visibility +
             lm[mp_pose.RIGHT_KNEE].visibility +
             lm[mp_pose.RIGHT_ANKLE].visibility)
    l_vis = (lm[mp_pose.LEFT_HIP].visibility +
             lm[mp_pose.LEFT_KNEE].visibility +
             lm[mp_pose.LEFT_ANKLE].visibility)

    # Use visibility if the difference is meaningful (> 0.3 total)
    if abs(r_vis - l_vis) > 0.3:
        return _right_side() if r_vis > l_vis else _left_side()

    # Fall back to hip x-position (smaller x = that side is closer to camera)
    r_hip_x = lm[mp_pose.RIGHT_HIP].x
    l_hip_x = lm[mp_pose.LEFT_HIP].x
    return _right_side() if r_hip_x < l_hip_x else _left_side()


def get_side_debug_info(lm, preferred_side="auto") -> str:
    """Return a one-line debug string showing side selection + visibility scores."""
    mp_pose = mp.solutions.pose.PoseLandmark
    r_vis = (lm[mp_pose.RIGHT_HIP].visibility +
             lm[mp_pose.RIGHT_KNEE].visibility +
             lm[mp_pose.RIGHT_ANKLE].visibility)
    l_vis = (lm[mp_pose.LEFT_HIP].visibility +
             lm[mp_pose.LEFT_KNEE].visibility +
             lm[mp_pose.LEFT_ANKLE].visibility)

    if preferred_side in ("right", "left"):
        chosen = preferred_side.upper()
        mode = "MANUAL"
    else:
        if abs(r_vis - l_vis) > 0.3:
            chosen = "RIGHT" if r_vis > l_vis else "LEFT"
            mode = "AUTO(vis)"
        else:
            r_hip_x = lm[mp_pose.RIGHT_HIP].x
            l_hip_x = lm[mp_pose.LEFT_HIP].x
            chosen = "RIGHT" if r_hip_x < l_hip_x else "LEFT"
            mode = "AUTO(pos)"

    return (f"{mode}->{chosen}  "
            f"R:{r_vis:.2f} L:{l_vis:.2f}")


def is_side_visible(lm, threshold=0.08):
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

    def torso_lean_excessive(self, lm, frame, side):
        h, w, _ = frame.shape
        hip = lm[side["hip"]]
        sh = lm[side["shoulder"]]

        hip_pt = np.array([hip.x*w, hip.y*h])
        sh_pt = np.array([sh.x*w, sh.y*h])

        v = sh_pt - hip_pt
        angle = abs(np.degrees(np.arctan2(v[0], -v[1])))

        return angle > self.TORSO_MAX

    def heels_lifted(self, lm, side):
        foot = lm[side["foot_index"]]
        heel = lm[side["heel"]]
        return (foot.y - heel.y) > self.HEEL_THRESH

    def knee_too_far_forward(self, lm, side):
        knee = lm[side["knee"]]
        foot = lm[side["foot_index"]]
        # When RIGHT leg faces camera: knee passes foot if knee.x > foot.x (rightward)
        # When LEFT leg faces camera: knee passes foot if knee.x < foot.x (leftward)
        if side["knee"] == mp.solutions.pose.PoseLandmark.RIGHT_KNEE:
            return (knee.x - foot.x) > self.KNEE_FWD_THRESH
        else:
            return (foot.x - knee.x) > self.KNEE_FWD_THRESH

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

    def update(self, lm, frame, preferred_side="auto"):

        side = get_visible_side(lm, preferred_side)
        side_ok = is_side_visible(lm)

        lean_bad = self.torso_lean_excessive(lm, frame, side)
        heels_bad = self.heels_lifted(lm, side)
        knee_fwd_bad = self.knee_too_far_forward(lm, side)

        sh_lm = lm[side["shoulder"]]

        hip_lm = lm[side["hip"]]
        knee_lm = lm[side["knee"]]
        ankle_lm = lm[side["ankle"]]

        hip = [hip_lm.x, hip_lm.y]
        knee = [knee_lm.x, knee_lm.y]
        ankle = [ankle_lm.x, ankle_lm.y]

        knee_angle = calculate_angle(hip, knee, ankle)

        foot_lm = lm[side["foot_index"]]
        heel_lm = lm[side["heel"]]

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

        voice_msgs = []

        if not side_ok:
            draw_warning(frame, "TURN SIDEWAYS", 120)
            voice_msgs.append("Please turn sideways to the camera")

        if visual_state == self.GOOD and self.last_state == "UP":
            voice_msgs.append("Well done, great squat!")

        if visual_state == self.BAD:
            y = 140
            if errors["knee_depth"]:
                draw_warning(frame, "Incorrect squat depth", y); y += 40
                voice_msgs.append("Adjust your squat depth, bend your knees more")
            if errors["torso"]:
                draw_warning(frame, "Excessive torso lean", y); y += 40
                voice_msgs.append("Keep your back straight, do not lean forward")
            if errors["heels"]:
                draw_warning(frame, "Heels lifted", y); y += 40
                voice_msgs.append("Keep your heels on the ground")
            if errors["knee_forward"]:
                draw_warning(frame, "Knee past toes", y)
                voice_msgs.append("Push your knees back, do not go past your toes")

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

        return knee_angle, self.rep_count, color, voice_msgs


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
        # Start as BENT so person must extend first — prevents false count at startup
        self.last_state = "BENT"
        self.rep_count = 0
        self.total_rep_count = 0

        self.hip_ref_y = None

        self.KNEE_MIN = 105            # leg is bent below this
        self.KNEE_MAX = 150            # leg is extended above this
        self.TORSO_MAX = 35           # degrees (slightly lenient for seated posture)
        self.HIP_LIFT_THRESH = 0.02

    def torso_lean_excessive(self, lm, frame, side):
        h, w, _ = frame.shape
        hip = lm[side["hip"]]
        sh = lm[side["shoulder"]]

        hip_pt = np.array([hip.x*w, hip.y*h])
        sh_pt = np.array([sh.x*w, sh.y*h])

        v = sh_pt - hip_pt
        angle = abs(np.degrees(np.arctan2(v[0], -v[1])))

        return angle > self.TORSO_MAX

    def hip_lifted(self, lm, side):
        hip = lm[side["hip"]]
        if self.hip_ref_y is None:
            return False
        return abs(hip.y - self.hip_ref_y) > self.HIP_LIFT_THRESH

    def evaluate_form(self, lean_bad, hip_bad):
        errors = {
            "torso": lean_bad,
            "hip": hip_bad,
        }

        if any(errors.values()):
            return self.BAD, errors
        return self.GOOD, errors

    def update(self, lm, frame, preferred_side="auto"):

        side = get_visible_side(lm, preferred_side)
        side_ok = is_side_visible(lm)

        sh_lm = lm[side["shoulder"]]
        hip_lm = lm[side["hip"]]
        knee_lm = lm[side["knee"]]
        ankle_lm = lm[side["ankle"]]

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

        # Set hip reference when the leg is extended (stable seated position)
        if motion == "EXTENDED" and self.hip_ref_y is None:
            self.hip_ref_y = hip_lm.y

        lean_bad = self.torso_lean_excessive(lm, frame, side)
        hip_bad = self.hip_lifted(lm, side)

        # Use a more lenient threshold for seated sideways check
        seated_side_ok = is_side_visible(lm, threshold=0.15)

        visual_state = self.NEUTRAL
        errors = {}

        if seated_side_ok and motion == "BENT":
            if self.last_state == "EXTENDED":
                self.total_rep_count += 1
            visual_state, errors = self.evaluate_form(
                lean_bad, hip_bad)

            if visual_state == self.GOOD and self.last_state == "EXTENDED":
                self.rep_count += 1

        color = self.STATE_COLORS[visual_state]
        voice_msgs = []

        if not seated_side_ok:
            draw_warning(frame, "TURN SIDEWAYS", 120)
            voice_msgs.append("Please turn sideways to the camera")

        if visual_state == self.GOOD and self.last_state == "EXTENDED":
            voice_msgs.append("Well done, great knee bend!")

        if visual_state == self.BAD:
            y = 160
            if errors["torso"]:
                draw_warning(frame, "Do not lean backward", y); y += 40
                voice_msgs.append("Keep your back straight, do not lean backward")
            if errors["hip"]:
                draw_warning(frame, "Keep your hip on the chair", y)
                voice_msgs.append("Keep your hip on the chair, do not lift up")

        draw_landmark(frame, sh_lm, color)
        draw_line(frame, hip_lm, sh_lm, color)

        draw_landmark(frame, hip_lm, color)
        draw_landmark(frame, knee_lm, color)
        draw_landmark(frame, ankle_lm, color)

        draw_line(frame, hip_lm, knee_lm, color)
        draw_line(frame, knee_lm, ankle_lm, color)

        self.last_state = motion

        return knee_angle, self.rep_count, color, voice_msgs

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
        # Start as "UP" (leg flat/resting) so person must raise leg first
        # before any rep can be counted — prevents false count at startup
        self.last_state = "UP"
        self.rep_count = 0
        self.total_rep_count = 0

        # Per-side rep tracking
        self.left_rep_count = 0
        self.left_total_rep_count = 0
        self.right_rep_count = 0
        self.right_total_rep_count = 0
        self.current_side = "right"  # which side is currently active

        self.KNEE_STRAIGHT = 160
        self.HIP_RAISE_MIN = 140     # degrees
        self.TORSO_MAX = 20

    def _detect_raised_leg(self, lm):
        """Auto-detect which leg is being raised by comparing ankle heights.
        The raised leg's ankle will have a lower y value (higher on screen).
        """
        mp_pose = mp.solutions.pose.PoseLandmark
        r_ankle = lm[mp_pose.RIGHT_ANKLE]
        l_ankle = lm[mp_pose.LEFT_ANKLE]
        r_knee = lm[mp_pose.RIGHT_KNEE]
        l_knee = lm[mp_pose.LEFT_KNEE]

        # Compare how high each ankle is relative to its knee
        # (more negative = leg raised higher)
        r_raise = r_knee.y - r_ankle.y
        l_raise = l_knee.y - l_ankle.y

        if r_raise > l_raise:
            return "right"
        else:
            return "left"

    def torso_lifted(self, lm, frame, side):
        h, w, _ = frame.shape
        hip = lm[side["hip"]]
        sh = lm[side["shoulder"]]

        hip_pt = np.array([hip.x * w, hip.y * h])
        sh_pt = np.array([sh.x * w, sh.y * h])

        v = sh_pt - hip_pt
        # Measure angle from horizontal using absolute values — works for both
        # left and right facing directions
        angle_from_horiz = abs(np.degrees(np.arctan2(abs(v[1]), abs(v[0]) + 1e-6)))
        return angle_from_horiz > self.TORSO_MAX

    def evaluate_form(self, knee_bad, hip_bad, torso_bad):
        errors = {
            "knee": knee_bad,
            "hip": hip_bad,
            "torso": torso_bad
        }

        if any(errors.values()):
            return self.BAD, errors
        return self.GOOD, errors

    def update(self, lm, frame, preferred_side="auto"):

        # Auto-detect which leg is raised
        if preferred_side == "auto":
            detected = self._detect_raised_leg(lm)
            side = get_visible_side(lm, detected)
            self.current_side = detected
        else:
            side = get_visible_side(lm, preferred_side)
            self.current_side = preferred_side

        sh_lm = lm[side["shoulder"]]
        hip_lm = lm[side["hip"]]
        knee_lm = lm[side["knee"]]
        ankle_lm = lm[side["ankle"]]

        shoulder = [sh_lm.x, sh_lm.y]
        hip = [hip_lm.x, hip_lm.y]
        knee = [knee_lm.x, knee_lm.y]
        ankle = [ankle_lm.x, ankle_lm.y]

        knee_angle = calculate_angle(hip, knee, ankle)
        hip_angle = calculate_angle(shoulder, hip, knee)

        # UP = leg resting flat (hip_angle near 180°)
        # DOWN = leg raised (hip_angle decreases as leg lifts)
        if hip_angle > self.HIP_RAISE_MIN:
            motion = "UP"
        else:
            motion = "DOWN"

        knee_bad = knee_angle < self.KNEE_STRAIGHT
        hip_bad = hip_angle < self.HIP_RAISE_MIN
        torso_bad = self.torso_lifted(lm, frame, side)

        visual_state = self.NEUTRAL
        errors = {}

        # Count rep when leg returns to resting (UP) after being raised (DOWN)
        # No sideways requirement — SLR is valid lying on back or on side
        if motion == "UP":
            if self.last_state == "DOWN":
                self.total_rep_count += 1
                if self.current_side == "left":
                    self.left_total_rep_count += 1
                else:
                    self.right_total_rep_count += 1

            visual_state, errors = self.evaluate_form(
                knee_bad, hip_bad, torso_bad
            )

            if visual_state == self.GOOD and self.last_state == "DOWN":
                self.rep_count += 1
                if self.current_side == "left":
                    self.left_rep_count += 1
                else:
                    self.right_rep_count += 1

        color = self.STATE_COLORS[visual_state]
        voice_msgs = []

        if visual_state == self.GOOD and self.last_state == "DOWN":
            side_name = "left" if self.current_side == "left" else "right"
            voice_msgs.append(f"Well done, great {side_name} leg raise!")

        if visual_state == self.BAD:
            y = 160
            if errors["knee"]:
                draw_warning(frame, "Keep knee straight", y); y += 40
                voice_msgs.append("Keep your knee straight, do not bend it")
            if errors["hip"]:
                draw_warning(frame, "Raise leg higher", y); y += 40
                voice_msgs.append("Try to raise your leg a bit higher")
            if errors["torso"]:
                draw_warning(frame, "Do not lift trunk", y)
                voice_msgs.append("Keep your upper body flat, do not lift your trunk")

        # Show which leg is being tracked
        side_label = "LEFT" if self.current_side == "left" else "RIGHT"
        cv2.putText(frame, f"Leg: {side_label}", (30, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2, cv2.LINE_AA)

        draw_landmark(frame, sh_lm, color)
        draw_line(frame, hip_lm, sh_lm, color)

        draw_landmark(frame, hip_lm, color)
        draw_landmark(frame, knee_lm, color)
        draw_landmark(frame, ankle_lm, color)

        draw_line(frame, hip_lm, knee_lm, color)
        draw_line(frame, knee_lm, ankle_lm, color)

        self.last_state = motion

        return knee_angle, hip_angle, self.rep_count, color, voice_msgs
