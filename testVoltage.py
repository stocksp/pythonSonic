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

print('Raw ADC Value: ', chan0.value)
print('ADC Voltage: ' + str(chan0.voltage * 5) + 'V')