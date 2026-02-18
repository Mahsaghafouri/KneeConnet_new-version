import speech_recognition as sr
import pyttsx3
from PyQt6.QtCore import QThread, pyqtSignal

class SpeechThread(QThread):
    result = pyqtSignal(str)

    def run(self):
        engine = pyttsx3.init()
        recognizer = sr.Recognizer()

        with open("/Users/zohrehmahdavi/Desktop/OVGU/SD/Squats.txt", "r", encoding="utf-8") as f:
            instructions = f.read()
        # instructions = "Are you ready to start the exercise?"
        engine.say(instructions)
        engine.runAndWait()

        with sr.Microphone() as source:
            audio = recognizer.listen(source)

        try:
            text = recognizer.recognize_google(audio).lower()
            self.result.emit(text)
        except:
            self.result.emit("error")