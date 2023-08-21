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

# use implied rowid
TABLE_CREATE = "CREATE TABLE setting(target_temp REAL, last_position INT, onoff INT, \
    kp REAL, ki REAL, kd REAL, lower INT, upper INT, pos_margin INT)"
# This MUST be in table create order...
ROW_CREATE = "INSERT INTO setting VALUES(:target_temp, :last_position, :onoff, :kp, :ki, :kd, :lower, :upper, :pos_margin)"
SETTING_DEFAULTS = {
    "target_temp": 22.0,
    "last_position": 8000,
    "onoff": 1,
    "kp": 1.1,
    "ki": 0.7,
    "kd": 1.2,
    "lower": 1034,
    "upper": 24600,
    "pos_margin" : 50
}
UPDATE_RATE = 15
SPEED = 160000
UPSPEED = -SPEED
DOWNSPEED = SPEED

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
    def __init__(self, pid, stats):
        self.stats = stats
        self.settingsfile = "settings.sqlite"
        # if not file, setup schema and default row.
        self.checkCreateDB()
        self.pid = pid
        self.update(startup=True)

    def checkCreateDB(self):
        self.con = sqlite3.connect(self.settingsfile)
        self.con.row_factory = sqlite3.Row
        # check if table exists:
        res = self.con.execute('''SELECT name FROM sqlite_master WHERE type='table' AND name='setting';''').fetchone()
        if res is None:
            self.con.execute(TABLE_CREATE)
            self.con.commit()
        res = self.con.execute('''SELECT * FROM setting WHERE rowid=1;''').fetchone()
        if res is None:
            self.con.execute(ROW_CREATE, SETTING_DEFAULTS)
            self.con.commit()

    def update(self, startup=False):
        # query SQLite
        data = self.con.execute('''SELECT * FROM setting WHERE rowid=1;''').fetchone()
        self.pos_margin = data["pos_margin"]
        # load last position for init
        self.lastpos = data["last_position"]
        # update pid with new settings.
        self.pid.setpoint = data["target_temp"]
        self.pid.tunings = (data["kp"], data["ki"], data["kd"])
        self.pid.set_auto_mode(data["onoff"], data["last_position"])
        #not sure why I have that startup flag... I guess let's not update stats on startup??
        if not startup:
            self.stats.target.set(data["target_temp"])
            self.stats.kp.set(data["kp"])
            self.stats.ki.set(data["ki"])
            self.stats.kd.set(data["kd"])
            self.stats.onoff.state("on" if data["onoff"] else "off")

    def updatePostion(self, pos):
        self.con.execute('''UPDATE setting SET last_position = ? WHERE rowid=1;''', (pos,))
        self.con.commit()
        self.stats.position.set(pos)

class Controller:
    def __init__(self, settings):
        self.settings = settings
        self.stats = settings.stats
        i2c = busio.I2C(board.D1, board.D0)  # using i2c0
        self.POS = AnalogIn(ADS1015(i2c), P0)
        self.TEMP = adafruit_sht4x.SHT4x(i2c)
        self.TEMP.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION
        # PID setup and options.
        self.pid = PID(settings["kp"], settings["ki"], settings["kd"],
            setpoint=settings["last_position"], output_limits=(settings["lower"],settings["upper"]), auto_mode=settings["onoff"])
        self.pid.sample_time = UPDATE_RATE  # set PID update rate UPDATE_RATE
        self.pid.proportional_on_measurement = True
        # allow setpoint change spikes to get us to temp faster (?)
        self.pid.differential_on_measurement = False # Maybe disable this if it's adjusting the motors is too noisy

    def goUp(self, target):
        motors.motor2.setSpeed(UPSPEED)
        while self.POS.value < target:
            pass

    def goDown(self, target):
        motors.motor2.setSpeed(DOWNSPEED)
        while self.POS.value > target:
            pass

    def go(self, target):
        print(f"Current POS: { self.POS.value } Target: { target }")
        try:
            motors.setSpeeds(0, 0)
            motors.enable()
            # use asyncio to set a timeout on this.
            if self.POS.value > target+self.settings.pos_margin: self.goDown(target+self.settings.pos_margin)
            if self.POS.value < target-self.settings.pos_margin: self.goUp(target-self.settings.pos_margin)
            motors.setSpeeds(0, 0)
        finally:
          # Stop the motors, even if there is an exception
          # or the user presses Ctrl+C to kill the process.
          motors.setSpeeds(0, 0)
          motors.disable()

    def loop(self):
        lastupdate = time.monotonic()
        lastpos = self.settings.lastpos
        while True:
            currentupdate = time.monotonic()
            # measure
            temp, humidity = self.TEMP.measurements
            # Do things...
            newpos = round(self.pid(temp))
            print(f"Target: { self.pid.setpoint } Temp: {self. temp } PID Return: { self.newpos }")
            if newpos != lastpos: self.settings.updatePostion(newpos) # store new location
            # move to new setpoint
            self.go(newpos)

            # Log stats...
            self.stats.temp.set(temp)
            self.stats.humidity.set(humidity)

            # check for updated SQL values
            self.settings.update()
            time.sleep(max(2 - (currentupdate-lastupdate), 0)) # sleep at most 2 secs...
            lastupdate = currentupdate


if __name__ == '__main__':
    # Start up the server to expose the metrics.
    prometheus_client.start_http_server(8008)
    stats = Stats()
    control = Controller(Settings(pid, stats))
    control.loop()
