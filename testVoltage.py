from MCP3008 import MCP3008

adc = MCP3008()
value = adc.read( channel = 0 ) # You can of course adapt the channel to be read out
print("Applied voltage: %.2f" % (value / 1023.0 * 3.3) )