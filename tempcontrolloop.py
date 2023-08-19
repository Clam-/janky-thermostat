# Run this at boot to continuously poll and adjust temp.
import prometheus_client
from simple_pid import PID
from dual_mc33926 import motors
import board
import busio
from adafruit_ads1x15.ads1015 import ADS1015, P0
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_sht4x

import time
import os.path
import sqlite3

prometheus_client.REGISTRY.unregister(prometheus_client.GC_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PLATFORM_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PROCESS_COLLECTOR)

i2c = busio.I2C(board.D1, board.D0)  # using i2c0
POS = AnalogIn(ADS1015(i2c), P0)
TEMP = adafruit_sht4x.SHT4x(i2c)
TEMP.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION

# use implied rowid
TABLE_CREATE = "CREATE TABLE setting(target_temp REAL, last_position INT, onoff INT, \
    kp REAL, ki REAL, kd REAL, lower INT, upper INT)"
ROW_CREATE = "INSERT INTO setting VALUES(:target_temp, :last_position, :onoff, :ki, :kd, :kp, :lower, :upper)"
SETTING_DEFAULTS = {
    "target_temp": 22.0,
    "last_position": 8000,
    "onoff": 1,
    "kp": -1.1,
    "ki": -0.7,
    "kd": -1.2,
    "lower": 1034,
    "upper": 24600
}
UPDATE_RATE = 10
POS_MARGIN = 2
SPEED = 100

# Metric reportings
class Stats:
    def __init__(self):
        self.temp = prometheus_client.Gauge('temp', 'Temperature C')
        self.humidity = prometheus_client.Gauge('humid', 'Humidity %')
        self.target = prometheus_client.Gauge('target', 'Target C')
        self.position = prometheus_client.Gauge('position', 'Valve position')
        self.onoff = prometheus_client.Enum('onoff', 'Heating',
                states=['on', 'off'])
        self.onoff.state('on')
        self.kp = prometheus_client.Gauge('kp', 'Proportional')
        self.ki = prometheus_client.Gauge('ki', 'Integral')
        self.kd = prometheus_client.Gauge('kd', 'Derivative ')

# Settings management and storage
class Settings:
    def __init__(self, pid):
        self.settingsfile = "settings.sqlite"
        # if not file, setup schema and default row.
        self.checkCreateDB()
        self.pid = pid
        self.update(startup=True)

    def checkCreateDB(self):
        self.con = sqlite3.connect(self.settingsfile)
        con.row_factory = sqlite3.Row
        # check if table exists:
        if con.execute('''SELECT name FROM sqlite_master WHERE type='table' AND name='setting';''').rowcount < 1:
            con.execute(TABLE_CREATE)
        if con.execute('''SELECT * FROM setting WHERE rowid=1;''').rowcount < 1:
            con.execute(ROW_CREATE, SETTING_DEFAULTS)

    def update(self, stats, startup=False):
        # query SQLite
        con.execute('''SELECT * FROM setting WHERE rowid=1;''')
        data = con.fetchone()
        # load last position for init
        self.lastpos = data["last_position"]
        # update pid with new settings.
        self.pid.setpoint = data["target_temp"]
        stats.target = data["target_temp"]
        self.pid.tunings = (data["kp"], data["ki"], data["kd"])
        stats.kp = data["kp"]
        stats.ki = data["ki"]
        stats.kd = data["kd"]
        self.pid.set_auto_mode(data["onoff"], data["last_position"])
        stats.onoff = "on" if data["onoff"] else "off"

    def updatePostion(self, pos, stats):
        con.execute('''UPDATE setting SET last_position = ? WHERE rowid=1;''', pos)
        stats.position = pos


# PID setup and options.
pid = PID(SETTING_DEFAULTS["kp"], SETTING_DEFAULTS["ki"], SETTING_DEFAULTS["kd"],
    setpoint=1, output_limits=(SETTING_DEFAULTS["lower"],SETTING_DEFAULTS["upper"]), auto_mode=False)
pid.sample_time = UPDATE_RATE  # set PID update rate UPDATE_RATE
pid.proportional_on_measurement = True
# allow setpoint change spikes to get us to temp faster (?)
pid.differential_on_measurement = False # Maybe disable this if it's adjusting the motors is too noisy


stats = Stats()
settings = Settings(pid)


lastupdate = time.monotonic()

def goUp(target):
    motors.motor2.setSpeed(SPEED)
    while POS.value < target-POS_MARGIN:
        pass

def goDown(target):
    motors.motor2.setSpeed(-SPEED)
    while POS.value > target+POS_MARGIN:
        pass

def go(target):
    try:
        motors.setSpeeds(0, 0)
        motors.enable()
        # use asyncio to set a timeout on this.
        if target < POS.value: goUp(target)
        if target > POS.value: goDown(target)
        motors.setSpeeds(0, 0)
    finally:
      # Stop the motors, even if there is an exception
      # or the user presses Ctrl+C to kill the process.
      motors.setSpeeds(0, 0)
      motors.disable()

if __name__ == '__main__':
    # Start up the server to expose the metrics.
    prometheus_client.start_http_server(8000)
    lastpos = settings.lastpos
    while True:
        currentupdate = time.monotonic()
        # measure
        temp, humidity = TEMP.measurements
        # Do things...
        newpos = pid(temp)
        if newpos != lastpos: settings.updatePostion(newpos, stats) # store new location
        # move to new setpoint
        go(newpos)

        # Log stats...
        stats.temp.set = temp
        stats.humidity.set = humidity

        # check for updated SQL values
        settings.update(stats)
        time.sleep(max(2 - (currentupdate-lastupdate), 0)) # sleep at most 2 secs...
        lastupdate = currentupdate
