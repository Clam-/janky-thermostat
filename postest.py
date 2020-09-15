import time
import board
import busio
import adafruit_ads1x15.ads1015 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# Create the I2C bus
i2c = busio.I2C(board.SCL, board.SDA)
# Create the ADC object using the I2C bus
ads = ADS.ADS1015(i2c)
# Create single-ended input on channel 0
chan = AnalogIn(ads, ADS.P0)

print("{:>5}\t{:>5}".format('raw', 'v'))

while True:
    print("\r{:>5}\t{:>5.3f}".format(chan.value, chan.voltage), end="")
    time.sleep(0.1)
