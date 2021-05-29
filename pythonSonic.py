from dotenv import load_dotenv
import os
import RPi.GPIO as GPIO
import time
import glob

# import board
# import adafruit_hcsr04
from datetime import datetime, timezone, timedelta
import asyncio
from pymongo import MongoClient

from MCP3008 import MCP3008
from statistics import stdev
from statistics import mean

load_dotenv()
timezone_offset = -8.0  # Pacific Standard Time (UTC−08:00)
tzinfo = timezone(timedelta(hours=timezone_offset))
db = None
# used for sound calc
# temp sensor off for now
currentTemp = 30.0
# GPIO Mode (BOARD / BCM)
GPIO.setmode(GPIO.BCM)

# set GPIO Pins
GPIO_TRIGGER = 23
GPIO_ECHO = 24

# set GPIO direction (IN / OUT)
GPIO.setup(GPIO_TRIGGER, GPIO.OUT)
GPIO.setup(GPIO_ECHO, GPIO.IN)

base_dir = "/sys/bus/w1/devices/"
device_folder = glob.glob(base_dir + "28*")[0]
device_file = device_folder + "/w1_slave"


def read_temp_raw():
    f = open(device_file, "r")
    lines = f.readlines()
    f.close()
    return lines


def read_temp():
    lines = read_temp_raw()
    while lines[0].strip()[-3:] != "YES":
        time.sleep(0.5)
        lines = read_temp_raw()
    equals_pos = lines[1].find("t=")
    if equals_pos != -1:
        temp_string = lines[1][equals_pos + 2:]
        temp_c = float(temp_string) / 1000.0
        temp_f = temp_c * 9.0 / 5.0 + 32.0
        return temp_c, temp_f


def distance():
    timeout = 0.1
    try:
        # set Trigger to HIGH
        GPIO.output(GPIO_TRIGGER, True)

        # set Trigger after 0.01ms to LOW
        time.sleep(0.00001)
        GPIO.output(GPIO_TRIGGER, False)

        StartTime = time.time()
        StopTime = time.time()

        timestamp = time.monotonic()

        # save StartTime
        while GPIO.input(GPIO_ECHO) == 0:
            StartTime = time.time()
            if (time.monotonic() - timestamp) > timeout:
                raise RuntimeError("Timed out")

        # save time of arrival
        timestamp = time.monotonic()
        while GPIO.input(GPIO_ECHO) == 1:
            StopTime = time.time()
            if time.monotonic() - timestamp > timeout:
                raise RuntimeError("Timed out")

        # time difference between start and arrival
        TimeElapsed = StopTime - StartTime
        # multiply with the sonic speed (34300 cm/s)
        # and divide by 2, because there and back

        # speed of sound with temperature
        speedOfSound = (331.5 + (0.6 * currentTemp)) * 100
        print(f"Speed of sound {speedOfSound:.0f}")
        distance = (TimeElapsed * speedOfSound) / 2
        # convert to inches
        return distance * 0.3937008
    except Exception as err:
        print(f"Error reading sensor {err}", flush=True)
        return 0


async def voltage():
    adc = MCP3008()
    # lastVoltageWrite = 0
    lastVoltageUpdate = datetime.now(tzinfo)
    startingUp = True

    try:
        while True:
            value = adc.read(channel=0)
            # fudge factor added of .815
            voltage = value * 5 * 0.815 / 1023.0 * 3.3
            print(f"Voltage: {voltage:.2f}")
            # voltDiff = abs(voltage - lastVoltageUpdate)
            secDiff = (datetime.now(tzinfo) - lastVoltageUpdate).total_seconds()
            if startingUp or secDiff > 60 * 30:
                startingUp = False
                lastVoltageUpdate = datetime.now(tzinfo)
                if db:
                    try:
                        collection = db.voltage
                        x = collection.insert_one(
                            {
                                "voltage": round(voltage, 1),
                                "when": datetime.now(tzinfo),
                            }
                        )
                        print(f"db for voltage says {x} ", flush=True)
                    except Exception as err:
                        print(f"Error in mongo insert {err}", flush=True)

            await asyncio.sleep(15)
    except Exception as err:
        print(f"Error reading voltage {err}", flush=True)
        return 0


async def sonicSensor():
    distList = []
    lastUpdateValue = 0.0
    starting = True
    try:
        while True:
            theDist = distance()
            print("Measured Distance = %.1f inches" % theDist, flush=True)
            if len(distList) > 0:
                previousAve = round(mean(distList), 2)
            else:
                previousAve = 0.0
            if theDist != 0:
                distList.append(theDist)
            # keep reading until 6 elements
            if starting and len(distList) < 15:
                await asyncio.sleep(5)
                continue
            elif starting:
                starting = False
                standardDev = stdev(distList)
                ave = mean(distList)
                distList = list(filter(lambda x: abs(x - ave) < standardDev, distList))
                await asyncio.sleep(5)
                continue

            # ignore bad values?
            if abs(theDist - previousAve) > 2.0:
                print(f"ignoring {theDist}", flush=True)
                distList.pop()
                await asyncio.sleep(10)
                continue
            # keep list at 6 AND remove errors of 0
            if len(distList) > 15:
                distList.pop(0)
            currentAve = round(mean(distList), 2)
            msg = (
                f"{theDist:.1f} inches, previous ave = {previousAve:.1f},"
                f"current ave={currentAve:.1f},"
                f"lastUpdateValue={lastUpdateValue}"
            )
            print(msg)
            diffDist = abs(lastUpdateValue - currentAve)
            if diffDist > 0.1:
                print(f"Need to do a change update {diffDist}", flush=True)
                lastUpdate = datetime.now(tzinfo)
                lastUpdateValue = currentAve
                try:
                    if db:
                        collection = db.waterDistance
                        x = collection.insert_one(
                            {"distance": round(currentAve, 1), "when": lastUpdate}
                        )
                        print(f"db says {x} ", flush=True)
                except Exception as err:
                    print("mongodb insert failed for dist change", flush=True)
                    exception_type = type(err).__name__
                    print(exception_type, flush=True)

            # send an update if we haven't in an hour and half
            elif (datetime.now(tzinfo) - lastUpdate).total_seconds() > 60 * 30:
                print(
                    f"Need to do a timed update {(datetime.now(tzinfo) - lastUpdate).total_seconds()}",
                    flush=True,
                )
                lastUpdate = datetime.now(tzinfo)
                lastUpdateValue = currentAve
                try:
                    if db:
                        collection = db.waterDistance
                        x = collection.insert_one(
                            {"distance": currentAve, "when": lastUpdate}
                        )
                except Exception as err:
                    print("mongodb insert failed for dist past time", flush=True)
                    exception_type = type(err).__name__
                    print(exception_type, flush=True)

            await asyncio.sleep(10)

        # Reset by pressing CTRL + C
    except Exception as err:
        print(f"Error in Sonic sensor{err}", flush=True)


async def tempSensor():
    # DHT_SENSOR = Adafruit_DHT.DHT22
    sensor = {
        "name": "Tank Climate inside",
        "pin": 4,
        "lastTempUpdate": datetime.now(tzinfo),
        "temperature": 0,
        "dbTemperature": 0,
        "humidity": 0,
        "dbHumidity": 0,
    }
    try:
        while True:

            # humidity, temperature = Adafruit_DHT.read_retry(DHT_SENSOR, sensor["pin"])
            (temperature, f) = read_temp()
            if temperature != 0:
                global currentTemp
                currentTemp = temperature
                t = round(((temperature * 9) / 5 + 32), 1)
                h = 0
                print(
                    f"{sensor['name']} Temp= {t}*F Humidity={h}% at {sensor['lastTempUpdate'].strftime('%d/%m/%Y %H:%M:%S')}",
                    flush=True,
                )
                print(
                    f'Now ---> {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}',
                    flush=True,
                )
                sensor["humidity"] = h
                sensor["temperature"] = t
                print(
                    f'dbTemp={sensor["dbTemperature"]} newTemp={t} {sensor["name"]}',
                    flush=True,
                )
                if abs(sensor["dbTemperature"] - t) > 0.9:
                    tmp = f"{t} °F, humidity: {h}%"
                    print(f"Updating with change {sensor['name']}, {tmp}", flush=True)
                    sensor["lastTempUpdate"] = datetime.now(tzinfo)
                    if db:
                        sensor["dbTemperature"] = t
                        sensor["dbHumidity"] = h
                        try:
                            # print('we have a db')
                            collection = db.climate
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
                            collection = db.climate
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
                    f"Failed to retrieve data from temperature sensor {sensor['name']}",
                    flush=True,
                )
            await asyncio.sleep(15)
    except Exception as err:
        print(f"Error in temp sensor{err}", flush=True)


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
        await asyncio.gather(sonicSensor(), tempSensor(), voltage())

    asyncio.run(main())
    print("done")
