import time
import queue
import threading
from PyQt6.QtCore import QObject, pyqtSlot


class TTSWorker(QObject):
    """Background thread that speaks voice feedback using pyttsx3 with cooldown.

    Uses a plain threading.Thread (not QThread) because pyttsx3 on Windows
    needs its own COM-initialized thread with a dedicated engine instance.
    Inherits QObject so pyqtSlot works for signal connections.
    """

    def __init__(self, cooldown_seconds=4.0):
        super().__init__()
        self._queue = queue.Queue()
        self._run_flag = True
        self._cooldown = cooldown_seconds
        self._last_said = {}
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @pyqtSlot(str)
    def enqueue(self, message: str):
        now = time.time()
        last = self._last_said.get(message, 0)
        if now - last >= self._cooldown:
            self._last_said[message] = now
            self._queue.put(message)

    def _run(self):
        # Initialize COM for this thread (required on Windows for SAPI)
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except ImportError:
            pass

        engine = None
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 160)
            print("TTS engine initialized successfully")
        except Exception as e:
            print(f"TTS init failed: {e}, trying fallback...")
            engine = None

        # If pyttsx3 failed, try Windows SAPI directly
        if engine is None:
            try:
                self._run_sapi()
                return
            except Exception as e:
                print(f"SAPI fallback also failed: {e}")
                return

        while self._run_flag:
            try:
                msg = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                engine.say(msg)
                engine.runAndWait()
            except Exception as e:
                print(f"TTS speak error: {e}")
                # Reinitialize engine on error
                try:
                    engine = pyttsx3.init()
                    engine.setProperty("rate", 160)
                except Exception:
                    pass

        try:
            engine.stop()
        except Exception:
            pass

        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except (ImportError, Exception):
            pass

    def _run_sapi(self):
        """Fallback: use Windows SAPI directly via win32com."""
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        print("TTS using SAPI fallback")

        while self._run_flag:
            try:
                msg = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                speaker.Speak(msg)
            except Exception as e:
                print(f"SAPI speak error: {e}")

    def stop(self):
        self._run_flag = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
