import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn
import busio
# import digitalio
import board

spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)

# create the cs (chip select)
# cs = digitalio.DigitalInOut(board.D22)

# create the mcp object
mcp = MCP.MCP3008(spi, 0)

# create an analog input channel on pin 5
chan0 = AnalogIn(mcp, MCP.P0)
counter = 0
sampleSize = 50
rawData = []

while counter < sampleSize:
    # if counter == 50:
    #     print('Raw ADC Value 6: ', chan5.value)
    #     print('ADC Voltage 6: ' + str(chan5.voltage) + 'V')
    #     print('Raw ADC Value 4: ', chan3.value)
    #     print('ADC Voltage 4: ' + str(chan3.voltage) + 'V')

    rawData.append(
        (chan0.value, chan0.voltage)
    )  # noqa
    chan0 = AnalogIn(mcp, MCP.P0)
   
    counter += 1
print(rawData)