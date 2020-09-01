import time
from dual_mc33926_rpi import motors, MAX_SPEED

SPEEDS = [0,1,2,3,4,5,6,7,8,9,10,-1,-2,-3,-4,-5,-6,-7,-8,-9,-10]

try:
    motors.enable()
    motors.setSpeeds(0, 0)

    print("Motor 2 test")
    for s in SPEEDS:
        motors.motor2.setSpeed(s)
        time.sleep(0.100)
finally:
  # Stop the motors, even if there is an exception
  # or the user presses Ctrl+C to kill the process.
  motors.setSpeeds(0, 0)
  motors.disable()
