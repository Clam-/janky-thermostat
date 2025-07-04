import time
from dual_mc33926_rpi import motors, MAX_SPEED
# motor stuff needs to be called as root because it does weird GPIO things...

#SPEEDS = [0,1,2,3,4,5,6,7,8,9,10,-1,-2,-3,-4,-5,-6,-7,-8,-9,-10]
SPEEDS = []

try:
    motors.enable()
    motors.setSpeeds(0, 0)

    print("Motor 2 test")
    for s in SPEEDS+SPEEDS+SPEEDS:
        motors.motor2.setSpeed(s)
        time.sleep(0.100)

finally:
  # Stop the motors, even if there is an exception
  # or the user presses Ctrl+C to kill the process.
  motors.setSpeeds(0, 0)
  motors.disable()
