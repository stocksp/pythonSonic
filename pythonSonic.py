from dotenv import load_dotenv
import os
import RPi.GPIO as GPIO
import time
# import board
# import adafruit_hcsr04
from datetime import datetime, timezone, timedelta
from statistics import mean
import asyncio
from pymongo import MongoClient
import Adafruit_DHT

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
    try:
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
        # convert to inches
        return distance * 0.3937008
    except Exception as err:
        print(f'Error reading sensor {err}', flush=True)
        return 0


async def sonicSensor():
    distList = []
    lastUpdateValue = 0.0
    try:
        while True:
            theDist = distance()
            print("Measured Distance = %.1f inches" % theDist)
            if len(distList) > 0:
                previousAve = round(mean(distList), 2)
            else:
                previousAve = 0.0
            if theDist != 0:
                distList.append(theDist)
            # keep reading until 6 elements
            if len(distList) < 6:
                continue
            # keep list at 6 AND remove errors of 0
            if len(distList) > 6:
                distList.pop(0)
            currentAve = round(mean(distList), 2)
            msg = (
                f'{theDist:.1f} inches, previous ave = {previousAve:.1f},'
                f'current ave={currentAve:.1f},'
                f'lastUpdateValue={lastUpdateValue}'
            )
            print(msg)
            diffDist = abs(lastUpdateValue - currentAve)
            if diffDist > 0.1:
                print(f'Need to do a change update {diffDist}', flush=True)
                lastUpdate = datetime.now(tzinfo)
                lastUpdateValue = currentAve
                try:
                    if db:
                        collection = db.pythonTest
                        x = collection.insert_one(
                            {'distance': currentAve, 'when': lastUpdate}
                        )
                        print(f"db says {x} ", flush=True)
                except Exception as err:
                    print("mongodb insert failed for dist change", flush=True)
                    exception_type = type(err).__name__
                    print(exception_type, flush=True)

            # send an update if we haven't in an hour and half
            elif (datetime.now(tzinfo) - lastUpdate).total_seconds() > 60 * 30:
                print(
                    f'Need to do a timed update {(datetime.now(tzinfo) - lastUpdate).total_seconds()}', flush=True)
                lastUpdate = datetime.now(tzinfo)
                lastUpdateValue = currentAve
                try:
                    if db:
                        collection = db.pythonTest
                        x = collection.insert_one(
                            {'distance': currentAve, 'when': lastUpdate}
                        )
                except Exception as err:
                    print("mongodb insert failed for dist past time", flush=True)
                    exception_type = type(err).__name__
                    print(exception_type, flush=True)

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


async def tempSensor():
    DHT_SENSOR = Adafruit_DHT.DHT22
    sensor = {
            'name' : "Tank Climate inside",
            'pin' : 17,
            'lastTempUpdate' : datetime.now(tzinfo),
            'temperature' : 0,
            'dbTemperature' : 0,
            'humidity' : 0,
            'dbHumidity' : 0,
    }
    while True:

        humidity, temperature = Adafruit_DHT.read_retry(
            DHT_SENSOR, sensor["pin"])

        if humidity is not None and temperature is not None:
            t = round(((temperature * 9) / 5 + 32), 1)
            h = round(humidity, 1)
            print(
                f"{sensor['name']} Temp= {t}*F Humidity={h}% at {sensor['lastTempUpdate'].strftime('%d/%m/%Y %H:%M:%S')}",
                flush=True,
            )
            print(
                f'Now ---> {datetime.now(tzinfo).strftime("%d/%m/%Y %H:%M:%S")}')
            sensor["humidity"] = h
            sensor["temperature"] = t
            print(
                f'dbTemp={sensor["dbTemperature"]} newTemp={t} {sensor["name"]}')
            if (
                abs(sensor["dbTemperature"] - t) > 0.9
                or abs(sensor["dbHumidity"] - h) > 2
            ):
                tmp = f"{t} °F, humidity: {h}%"
                print(
                    f"Updating with change {sensor['name']}, {tmp}", flush=True)
                sensor["lastTempUpdate"] = datetime.now(tzinfo)
                if db:
                    sensor["dbTemperature"] = t
                    sensor["dbHumidity"] = h
                    try:
                        # print('we have a db')
                        collection = db.pythonTest
                        x = collection.insert_one(
                            {
                                "name": sensor["name"],
                                "when": datetime.now(tzinfo),
                                "temperature": t,
                                "humidity": h,
                            }
                        )
                        print(f"db says {x} ", flush=True)
                    except:
                        print("mongodb insert failed", flush=True)

                else:
                    print("no database available", flush=True)
            # send if more than 30 minutes
            elif (
                datetime.now(tzinfo) - sensor["lastTempUpdate"]
            ).total_seconds() > 60 * 30:
                sensor["lastTempUpdate"] = datetime.now(tzinfo)
                sensor["dbTemperature"] = t
                sensor["dbHumidity"] = h
                if db:
                    try:
                        # print('we have a db')
                        collection = db.pythonTest
                        x = collection.insert_one(
                            {
                                "name": sensor["name"],
                                "when": datetime.now(tzinfo),
                                "temperature": t,
                                "humidity": h,
                            }
                        )
                        print(f"db says {x} ", flush=True)
                    except:
                        print("mongodb insert failed", flush=True)

                else:
                    print("no database available", flush=True)
            elif True:
                message = (
                    f'temp diff= {abs(sensor["dbTemperature"] - t):.1f} '
                    f'hum diff= {abs(sensor["dbHumidity"] - h):.1f} {sensor["name"]}'
                )
                print(message)
                # print(f'temp diff= {abs(sensor["dbTemperature"] - t):.1f} hum diff= {abs(sensor["dbHumidity"] - h):.1f} {sensor["name"]}')

        else:
            print(
                f"Failed to retrieve data from humidity sensor {sensor['name']}",
                flush=True,
            )
        await asyncio.sleep(15)

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
        time.sleep(5)


if __name__ == "__main__":
    async def main():
        setup()
        # Schedule three calls *concurrently*:
        await asyncio.gather(
            sonicSensor(),
            tempSensor(),
        )

    asyncio.run(main())
    print('done')
