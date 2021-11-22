from dotenv import load_dotenv
import os
import RPi.GPIO as GPIO
import time
import glob
import sys
from time import sleep

# import board
# import adafruit_hcsr04
from datetime import datetime, timezone, timedelta
import asyncio
from pymongo import MongoClient

from MCP3008 import MCP3008
from statistics import stdev
from statistics import mean

import logging
from logging.handlers import RotatingFileHandler

load_dotenv()
timezone_offset = -8.0  # Pacific Standard Time (UTC−08:00)
tzinfo = timezone(timedelta(hours=timezone_offset))
db = {}
failedWrites = 0
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


# logging
log_formatter = logging.Formatter(
    "%(asctime)s %(levelname)s %(funcName)s(%(lineno)d) %(message)s"
)
logFile = "/home/pi/pythonSonic/applogs.txt"
my_handler = RotatingFileHandler(
    logFile, mode="a", maxBytes=2 * 1024 * 1024, backupCount=2, encoding=None, delay=0
)
my_handler.setFormatter(log_formatter)
my_handler.setLevel(logging.INFO)
app_log = logging.getLogger("root")
app_log.setLevel(logging.INFO)
app_log.addHandler(my_handler)

def read_temp_raw():
    f = open(device_file, "r")
    lines = f.readlines()
    f.close()
    return lines


def read_temp():
    lines = read_temp_raw()
    counter = 0
    while len(lines) == 0 and lines[0].strip()[-3:] != "YES" and counter < 3:
        counter += 1
        time.sleep(0.2)
        lines = read_temp_raw()
    if len(lines) >= 2:
        equals_pos = lines[1].find("t=")
        if equals_pos != -1:
            temp_string = lines[1][equals_pos + 2:]
            temp_c = float(temp_string) / 1000.0
            temp_f = temp_c * 9.0 / 5.0 + 32.0
            return temp_c, temp_f
    else:
        app_log.error("Failed to read temperature ")


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
        app_log.error(f"Error reading sensor {err}")
        return 0


async def voltage():
    adc = MCP3008()
    # lastVoltageWrite = 0
    lastVoltageUpdate = datetime.now(tzinfo)
    startingUp = True

    try:
        while True:
            count = 0
            vals = []
            while count < 50:
                val = adc.read(channel=0) * 5 * 0.9047 / 1023.0 * 3.3
                vals.append(val)
                count += 1
                await asyncio.sleep(0.1)
            voltage = mean(vals)

            print(f"Voltage: {voltage:.2f}")
            # voltDiff = abs(voltage - lastVoltageUpdate)
            secDiff = (datetime.now(tzinfo) - lastVoltageUpdate).total_seconds()
            if startingUp or secDiff > 60 * 30:
                startingUp = False
                lastVoltageUpdate = datetime.now(tzinfo)
                if 'Synology' in db:
                    try:
                        data = {
                            "voltage": round(voltage, 1),
                            "when": datetime.now(tzinfo),
                        }
                        collection = db['Synology'].voltage
                        x = collection.insert_one(data)
                        print(f"db for voltage Synology says {x} ", flush=True)
                    except Exception as err:
                        print(f"Error in mongo insert voltage Synology {err}", flush=True)
                if 'Atlas' in db:
                    try:
                        data = {
                            "voltage": round(voltage, 1),
                            "when": datetime.now(tzinfo),
                        }
                        collection = db['Atlas'].voltage
                        x = collection.insert_one(data)
                        print(f"db for voltage Atlas says {x} ", flush=True)

                    except Exception as err:
                        print(f"Error in mongo insert voltage Atlas {err}", flush=True)

            await asyncio.sleep(15)
    except Exception as err:
        print(f"Error reading voltage {err}", flush=True)
        return 0


async def sonicSensor():
    distList = []
    lastUpdateValue = 0.0
    starting = True
    global failedWrites
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
            else:
                print(f"ignoring {theDist}", flush=True)
                await asyncio.sleep(5)
                continue
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
            if abs(theDist - previousAve) > 2.0 or theDist == 0:
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
            app_log.info(msg)
            diffDist = abs(lastUpdateValue - currentAve)
            print(f"diff is {diffDist}", flush=True)
            if diffDist > 0.1:
                print(f"Need to do a change update {diffDist}", flush=True)
                lastUpdate = datetime.now(tzinfo)
                lastUpdateValue = currentAve
                try:
                    if 'Synology' in db:
                        data = {"distance": round(currentAve, 1), "when": lastUpdate}
                        collection = db['Synology'].waterDistance
                        x = collection.insert_one(data)
                        print(f"db Synology dist says {x} ", flush=True)

                except Exception as err:
                    print("mongodb insert failed for dist change Synology", flush=True)
                    exception_type = type(err).__name__
                    print(exception_type, flush=True)
                    failedWrites += 1
                try:
                    if 'Atlas' in db:
                        data = {"distance": round(currentAve, 1), "when": lastUpdate}
                        collection = db['Atlas'].waterDistance
                        x = collection.insert_one(data)
                        print(f"db Atlas dist says {x} ", flush=True)

                except Exception as err:
                    print("mongodb insert failed for dist change Atlas", flush=True)
                    exception_type = type(err).__name__
                    print(exception_type, flush=True)
                    failedWrites += 1

            # send an update if we haven't in an hour and half
            elif (datetime.now(tzinfo) - lastUpdate).total_seconds() > 60 * 30:
                print(
                    f"Need to do a timed update {(datetime.now(tzinfo) - lastUpdate).total_seconds()}",
                    flush=True,
                )
                lastUpdate = datetime.now(tzinfo)
                lastUpdateValue = currentAve
                try:
                    if 'Synology' in db:
                        data = {"distance": currentAve, "when": lastUpdate}
                        collection = db['Synology'].waterDistance
                        x = collection.insert_one(data)

                except Exception as err:
                    print("mongodb insert Synology failed for dist past time", flush=True)
                    exception_type = type(err).__name__
                    print(exception_type, flush=True)
                    failedWrites += 1
                try:
                    if 'Atlas' in db:
                        data = {"distance": currentAve, "when": lastUpdate}
                        collection = db['Atlas'].waterDistance
                        x = collection.insert_one(data)

                except Exception as err:
                    print("mongodb insert Atlas failed for dist past time", flush=True)
                    exception_type = type(err).__name__
                    print(exception_type, flush=True)
                    failedWrites += 1
            if failedWrites > 3:
                os.system(os.system("sudo reboot"))
            await asyncio.sleep(10)

        # Reset by pressing CTRL + C
    except Exception as err:
        print(f"Error in Sonic sensor{err}", flush=True)
        app_log.error(f"Error in Sonic sensor{err}")


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
            (temperature, f) = read_temp()
            if temperature != 0:
                global currentTemp
                currentTemp = temperature
                t = round(((temperature * 9) / 5 + 32), 1)
                h = 0
                msg = f"{sensor['name']} Temp= {t}*F Humidity={h}% at {sensor['lastTempUpdate'].strftime('%d/%m/%Y %H:%M:%S')}"
                print(
                    msg,
                    flush=True,
                )
                print(
                    f'Now ---> {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}',
                    flush=True,
                )
                app_log.info(msg)
                sensor["humidity"] = h
                sensor["temperature"] = t
                print(
                    f'dbTemp={sensor["dbTemperature"]} newTemp={t} {sensor["name"]}',
                    flush=True,
                )
                data = {
                    "name": sensor["name"],
                    "when": datetime.now(tzinfo),
                    "temperature": t,
                    "humidity": h,
                    }
                if abs(sensor["dbTemperature"] - t) > 0.9:
                    tmp = f"{t} °F, humidity: {h}%"
                    print(f"Updating with change {sensor['name']}, {tmp}", flush=True)
                    app_log.info(f"Updating with change {sensor['name']}, {tmp}")
                    sensor["lastTempUpdate"] = datetime.now(tzinfo)
                    if 'Synology' in db:
                        sensor["dbTemperature"] = t
                        sensor["dbHumidity"] = h
                        try:
                            # print('we have a db')
                            collection = db['Synology'].climate
                            x = collection.insert_one(data)
                            print(f"db says {x} ", flush=True)
                        except:
                            print("mongodb insert climate failed Synology", flush=True)
                            app_log.error("mongodb insert failed for temperature")
                    if 'Atlas' in db:
                        sensor["dbTemperature"] = t
                        sensor["dbHumidity"] = h
                        try:
                            # print('we have a db')
                            collection = db['Atlas'].climate
                            x = collection.insert_one(data)
                            print(f"db says {x} ", flush=True)
                        except:
                            print("mongodb insert climate failed Synology", flush=True)
                            app_log.error("mongodb insert failed for temperature")

                    else:
                        print("no database available", flush=True)
                        app_log.error("no database available in temperature")
                # send if more than 30 minutes
                elif (
                    datetime.now(tzinfo) - sensor["lastTempUpdate"]
                ).total_seconds() > 60 * 30:
                    sensor["lastTempUpdate"] = datetime.now(tzinfo)
                    sensor["dbTemperature"] = t
                    sensor["dbHumidity"] = h
                    if 'Synology' in db:
                        sensor["dbTemperature"] = t
                        sensor["dbHumidity"] = h
                        try:
                            # print('we have a db')
                            collection = db['Synology'].climate
                            x = collection.insert_one(data)
                            print(f"db says {x} ", flush=True)
                        except:
                            print("mongodb insert climate failed Synology", flush=True)
                            app_log.error("mongodb insert failed for temperature")
                    if 'Atlas' in db:
                        sensor["dbTemperature"] = t
                        sensor["dbHumidity"] = h
                        try:
                            # print('we have a db')
                            collection = db['Atlas'].climate
                            x = collection.insert_one(data)
                            print(f"db says {x} ", flush=True)
                        except:
                            print("mongodb insert climate failed Synology", flush=True)
                            app_log.error("mongodb insert failed for temperature")

                    else:
                        print("no database available", flush=True)
                elif True:
                    message = (
                        f'temp diff= {abs(sensor["dbTemperature"] - t):.1f} '
                        f'hum diff= {abs(sensor["dbHumidity"] - h):.1f} {sensor["name"]}'
                    )
                    print(message)
                    app_log.info(message)
                    # print(f'temp diff= {abs(sensor["dbTemperature"] - t):.1f} hum diff= {abs(sensor["dbHumidity"] - h):.1f} {sensor["name"]}')

            else:
                print(
                    f"Failed to retrieve data from temperature sensor {sensor['name']}",
                    flush=True,
                )
                app_log.error(
                    f"Failed to retrieve data from temperature sensor {sensor['name']}"
                )
            await asyncio.sleep(15)
    except Exception as err:
        print(f"Error in temp sensor{err}", flush=True)
        app_log.error(f"Error in temp sensor {err}")


def setup():
    mongoURISynology = os.getenv("MONGO_URL_SYNOLOGY")
    mongoURIAtlas = os.getenv("MONGO_URL_ATLAS")
    global db
    counter = 0
    while 'Atlas' not in db:
        try:
            client = MongoClient(mongoURIAtlas)
            db['Atlas'] = client.matchClub
            print("connected to mongodb Atlas!", flush=True)
        except Exception as err:
            print("failed to make MonbgoClient", flush=True)
            print(err, flush=True)
            counter = counter + 1
            if counter > 5:
                print("Forcing a system restart", flush=True)
                python = sys.executable
                os.execl(python, python, *sys.argv)
            sleep(5 + counter * 10)

    while 'Synology' not in db:
        try:
            client = MongoClient(mongoURISynology)
            db['Synology'] = client.water
            print("connected to mongodb Synology!", flush=True)
        except Exception as err:
            print("failed to make MonbgoClient for Synology", flush=True)
            print(err, flush=True)
            counter = counter + 1
            if counter > 5:
                print("Forcing a system restart", flush=True)
                python = sys.executable
                os.execl(python, python, *sys.argv)
            sleep(5 + counter * 10)


if __name__ == "__main__":

    async def main():
        setup()
        # Schedule three calls *concurrently*:
        await asyncio.gather(sonicSensor(), tempSensor(), voltage())

    asyncio.run(main())
    print("done")
