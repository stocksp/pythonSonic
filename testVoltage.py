from MCP3008 import MCP3008

adc = MCP3008()
value = adc.read( channel = 0 ) 
voltage = (value * 5 * 0.815/ 1023.0 * 3.3)
print("Applied voltage: %.2f" % (value * 5 * 0.815/ 1023.0 * 3.3) )
print(f'Voltage: {voltage:.2f}')