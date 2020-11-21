from sys import argv, exit
from dual_mc33926_rpi import motors, MAX_SPEED
from time import sleep
from board import SCL, SDA
from busio import I2C
from adafruit_ads1x15.ads1015 import ADS1015, P0
from adafruit_ads1x15.analog_in import AnalogIn

if len(argv) != 2:
    print("Need position")
    exit(1)

try:
    POS = int(argv[1])
except:
    print("Invalid position")
    exit(1)
# set sane min/max (even though linear actuator will stop at the ends.)
if POS <= 1034:
    POS = 1034
elif POS >= 24600:
    POS = 24600
MIN = POS-10
MAX = POS+10

# Create the I2C bus # Create the ADC object using the I2C bus
# Create single-ended input on channel 0
chan = AnalogIn(ADS1015(I2C(SCL, SDA)), P0)

try:
    motors.setSpeeds(0, 0)
    motors.enable()

    if chan.value < MIN:
        motors.motor2.setSpeed(100)
        while chan.value < MIN:
            print("\r{:>5}\t{:>5.3f}".format(chan.value, chan.voltage), end="")
        motors.setSpeeds(0, 0)
    if chan.value > MAX:
        motors.motor2.setSpeed(-100)
        while chan.value > MAX:
            print("\r{:>5}\t{:>5.3f}".format(chan.value, chan.voltage), end="")
        motors.setSpeeds(0, 0)
finally:
  # Stop the motors, even if there is an exception
  # or the user presses Ctrl+C to kill the process.
  motors.setSpeeds(0, 0)
  motors.disable()
