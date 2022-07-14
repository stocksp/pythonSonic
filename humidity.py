import time
import board
import adafruit_dht
import psutil
import requests

from datetime import datetime, timezone, timedelta

timezone_offset = -8.0  # Pacific Standard Time (UTC−08:00)
tzinfo = timezone(timedelta(hours=timezone_offset))

addClimateURL = "http://ubuntu/api/addClimate"
addClimateTestURL = "http://ubuntu/api/addClimateTest"

# We first check if a libgpiod process is running. If yes, we kill it!
for proc in psutil.process_iter():
    if proc.name() == 'libgpiod_pulsein' or proc.name() == 'libgpiod_pulsei':
        proc.kill()

DHT_SENSOR = Adafruit_DHT.DHT22
sensor = dict(
            name="Crawl Space",
            pin=4,
            lastTempUpdate=datetime.now(tzinfo),
            temperature=0,
            dbTemperature=0,
            humidity=0,
            dbHumidity=0,
        )
while True:

    try:
        humidity, temperature = Adafruit_DHT.read_retry( DHT_SENSOR, sensor["pin"])
        print("Temperature: {}*C   Humidity: {}% ".format(temperature, humidity))
        if t != 0:
            global currentTemp
            currentTemp = temperature
            t = round(((temperature * 9) / 5 + 32), 1)
            h = round(humidity, 1)
            msg = f"{sensor['name']} Temp= {t}*F Humidity={h}% at {sensor['lastTempUpdate'].strftime('%d/%m/%Y %H:%M:%S')}"
            print(
                msg,
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
                
                sensor["dbTemperature"] = t
                sensor["dbHumidity"] = h
                    
                data = {
                        "name": sensor["name"],
                        "when": datetime.now(tzinfo),
                        "temperature": t,
                        "humidity": h,}
                
                r = requests.post(addClimateTestURL, data=data, timeout=10.0)
                print(f"local mongo db says {r.text} ", flush=True)
                        
                
            # send if more than 30 minutes
            elif (datetime.now(tzinfo) - sensor["lastTempUpdate"] ).total_seconds() > 60 * 30:
                sensor["lastTempUpdate"] = datetime.now(tzinfo)
                sensor["dbTemperature"] = t
                sensor["dbHumidity"] = h
                try:  
                    data = {
                            "name": sensor["name"],
                            "when": datetime.now(tzinfo),
                            "temperature": t,
                            "humidity": h,
                        }
                    r = requests.post(addClimateTestURL, data=data, timeout=10.0)
                    print(f"local mongo db says {r.text} ", flush=True)
                except:
                    print("request after 30 minutes failed", flush=True)


            elif True:
                message = (
                    f'temp diff= {abs(sensor["dbTemperature"] - t):.1f} '
                    f'hum diff= {abs(sensor["dbHumidity"] - h):.1f} {sensor["name"]}'
                )
                print(message)

            else:
                print(
                    f"Failed to retrieve data from temperature sensor {sensor['name']}",
                    flush=True,
                )
    except RuntimeError as error:
        print(error.args[0])
        time.sleep(2.0)
        continue
    except Exception as error:
        sensor.exit()
        raise error

    time.sleep(2.0)
