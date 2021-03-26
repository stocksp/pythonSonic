from dotenv import load_dotenv
import os
from time import sleep
import board
import adafruit_hcsr04
from datetime import datetime, timezone, timedelta

import asyncio
from pymongo import MongoClient

load_dotenv()
timezone_offset = -8.0  # Pacific Standard Time (UTC−08:00)
tzinfo = timezone(timedelta(hours=timezone_offset))
db = None

""" mongoURI = os.getenv("MONGO_URL")
print(mongoURI)

sonar = adafruit_hcsr04.HCSR04(trigger_pin=board.D23, echo_pin=board.D24)
while True:
    try:
        print((sonar.distance,))
    except RuntimeError:
        print("Retrying!")
    time.sleep(0.1)
 """
async def sonicSensor():
    sonar = adafruit_hcsr04.HCSR04(trigger_pin=board.D23, echo_pin=board.D24)
    try:
        print((sonar.distance,))
    except RuntimeError:
        print("Retrying!")

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