from dotenv import load_dotenv
import os
import time
import board
import adafruit_hcsr04

load_dotenv()

mongoURI = os.getenv("MONGO_URL")
print(mongoURI)

try:
    print((sonar.distance,))
except RuntimeError:
    print("Retrying!")