from dotenv import load_dotenv
import os
import RPi.GPIO as GPIO
import time
#import board
#import adafruit_hcsr04
from datetime import datetime, timezone, timedelta

import asyncio
from pymongo import MongoClient

load_dotenv()
timezone_offset = -8.0  # Pacific Standard Time (UTC−08:00)
tzinfo = timezone(timedelta(hours=timezone_offset))
db = None
# GPIO Mode (BOARD / BCM)
GPIO.setmode(GPIO.BCM)

# set GPIO Pins
GPIO_TRIGGER = 23
GPIO_ECHO = 24

# set GPIO direction (IN / OUT)
GPIO.setup(GPIO_TRIGGER, GPIO.OUT)
GPIO.setup(GPIO_ECHO, GPIO.IN)

def distance():
    # set Trigger to HIGH
    GPIO.output(GPIO_TRIGGER, True)

    # set Trigger after 0.01ms to LOW
    time.sleep(0.00001)
    GPIO.output(GPIO_TRIGGER, False)

    StartTime = time.time()
    StopTime = time.time()

    # save StartTime
    while GPIO.input(GPIO_ECHO) == 0:
        StartTime = time.time()

    # save time of arrival
    while GPIO.input(GPIO_ECHO) == 1:
        StopTime = time.time()

    # time difference between start and arrival
    TimeElapsed = StopTime - StartTime
    # multiply with the sonic speed (34300 cm/s)
    # and divide by 2, because there and back
    distance = (TimeElapsed * 34300) / 2
    #convert to inches
    return distance * 0.3937008

async def sonicSensor():
    try:
        while True:
            dist = distance()
            print("Measured Distance = %.1f cm" % dist)
            await asyncio.sleep(5)

        # Reset by pressing CTRL + C
    except KeyboardInterrupt:
        print("Measurement stopped by User")
        GPIO.cleanup()
    
    # while True:
    #     goodRead = True
    #     try:
    #         val = sonar.distance * 0.3937008
    #     except RuntimeError:
    #         print("Retrying!")
    #         goodRead = False
    #     if goodRead:
    #         print(f'dist= {val}')
        

def setup():
    mongoURI = os.getenv("MONGO_URL")
    global db
    while not db:
        try:
            client = MongoClient(mongoURI)
            db = client.matchClub
            print("connected to mongodb!", flush=True)
        except Exception as err:
            print("failed to make MonbgoClient", flush=True)
            print(err, flush=True)
        sleep(5)

if __name__ == "__main__":
    async def main():
        setup()
        # Schedule three calls *concurrently*:
        await asyncio.gather(
            sonicSensor(),
            # tempSensors(),
        )

    asyncio.run(main())
    print('done')