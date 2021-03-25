from dotenv import load_dotenv
import os
import time
import board
import adafruit_hcsr04

load_dotenv()

mongoURI = os.getenv("MONGO_URL")
print(mongoURI)

sonar = adafruit_hcsr04.HCSR04(trigger_pin=board.D23, echo_pin=board.D24)
try:
    print((sonar.distance,))
except RuntimeError:
    print("Retrying!")