# Run this at boot to continuously poll and adjust temp.
import queue
import prometheus_client
from simple_pid import PID
from dual_mc33926 import motors
import board
import busio
from adafruit_ads1x15.ads1115 import ADS1115, P0
from adafruit_ads1x15.ads1x15 import Mode
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_sht4x
import csv

import time
import sqlite3
import threading

prometheus_client.REGISTRY.unregister(prometheus_client.GC_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PLATFORM_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PROCESS_COLLECTOR)

# use implied rowid
TABLE_CREATE = "CREATE TABLE setting(target_temp REAL, last_position INT, onoff INT, \
    kp REAL, ki REAL, kd REAL, lower INT, upper INT, pos_margin INT, new_pos INT)"
TABLE_SCHED_CREATE = "CREATE TABLE schedule(timestamp TEXT PRIMARY KEY, temp REAL)"

# This MUST be in table create order...
ROW_CREATE = "INSERT INTO setting VALUES(:target_temp, :last_position, :onoff, :kp, :ki, :kd, :lower, :upper, :pos_margin, :new_pos)"
SETTING_DEFAULTS = {
    "target_temp": 22.0,
    "last_position": 8000,
    "onoff": 1,
    "kp": 1.1,
    "ki": 0.7,
    "kd": 1.2,
    "lower": 1034,
    "upper": 24600,
    "pos_margin" : 50,
    "new_pos": 0
}
UPDATE_RATE = 15
SPEED = 180000
UPSPEED = -SPEED
DOWNSPEED = SPEED
UP = 1
DOWN = -1
STOP = 0

# Metric reportings
class Stats:
    def __init__(self):
        self.temp = prometheus_client.Gauge('temp', 'Temperature C')
        self.humidity = prometheus_client.Gauge('humid', 'Humidity %')
        self.target = prometheus_client.Gauge('target', 'Target C')
        self.position = prometheus_client.Gauge('position', 'Desired position')
        self.onoff = prometheus_client.Enum('onoff', 'Heating', states=['on', 'off'])
        self.onoff.state('on')
        self.kp = prometheus_client.Gauge('kp', 'Proportional')
        self.ki = prometheus_client.Gauge('ki', 'Integral')
        self.kd = prometheus_client.Gauge('kd', 'Derivative ')
        self.ap = prometheus_client.Gauge('ap', "Calc'd Prop.") #--
        self.ai = prometheus_client.Gauge('ai', "Calc'd Int.")
        self.ad = prometheus_client.Gauge('ad', "Calc'd Deriv.")

# Settings management and storage
class Settings:
    def __init__(self, stats):
        self.stats = stats
        self.settingsfile = "settings.sqlite"
        # if not file, setup schema and default row.
        self.checkCreateDB()
        self.pid = None
        self.new_pos = None
        self.update(startup=True)

    def checkCreateDB(self):
        self.con = sqlite3.connect(self.settingsfile)
        self.con.row_factory = sqlite3.Row
        # check if table exists:
        res = self.con.execute('''SELECT name FROM sqlite_master WHERE type='table' AND name='setting';''').fetchone()
        if res is None:
            self.con.execute(TABLE_CREATE)
            self.con.commit()
        res = self.con.execute('''SELECT name FROM sqlite_master WHERE type='table' AND name='schedule';''').fetchone()
        if res is None:
            self.con.execute(TABLE_SCHED_CREATE)
            self.con.commit()
        res = self.con.execute('''SELECT * FROM setting WHERE rowid=1;''').fetchone()
        if res is None:
            self.con.execute(ROW_CREATE, SETTING_DEFAULTS)
            self.con.commit()
    def resetNewPos(self):
        self.con.execute('''UPDATE setting SET new_pos = ? WHERE rowid=1;''', (0,))
        self.con.commit()
        self.new_pos = 0

    def update(self, startup=False):
        # query SQLite
        data = self.con.execute('''SELECT * FROM setting WHERE rowid=1;''').fetchone()
        self.pos_margin = data["pos_margin"]
        # load last position for init
        self.last_position = data["last_position"]
        self.new_pos = data["new_pos"]
        self.onoff = data["onoff"]
        self.lower = data["lower"]
        self.upper = data["upper"]
        #not sure why I have that startup flag... I guess let's not update stats on startup??
        if startup:
            self.pid = PID(data["kp"], data["ki"], data["kd"], setpoint=data["target_temp"],
                output_limits=(data["lower"], data["upper"]), auto_mode=self.onoff, starting_output=self.last_position)
        else:
            self.stats.target.set(data["target_temp"])
            self.stats.kp.set(data["kp"])
            self.stats.ki.set(data["ki"])
            self.stats.kd.set(data["kd"])
            self.stats.onoff.state("on" if self.onoff else "off")
        # update pid with new settings.
        self.pid.setpoint = data["target_temp"]
        self.pid.tunings = (data["kp"], data["ki"], data["kd"])
        self.pid.set_auto_mode(data["onoff"], data["last_position"])
        # log PID component values:
        components = self.pid.components
        self.stats.ap.set(components[0])
        self.stats.ai.set(components[1])
        self.stats.ad.set(components[2])

    def updatePostion(self, pos):
        self.con.execute('''UPDATE setting SET last_position = ? WHERE rowid=1;''', (pos,))
        self.con.commit()
        self.stats.position.set(pos)
    
    def fetchsched(self, currstamp):
        return self.con.execute('''SELECT * FROM schedule WHERE timestamp <= ? ORDER BY timestamp DESC;''', (currstamp, )).fetchone()

# e.g. pos = ewma.new(npos) # filter
class EWMAFilter:
    def __init__(self, span):
        self.alpha = 2 / (span + 1)
        self.smoothed_value = None
    def new(self, new_input):
        if self.smoothed_value is None:
            self.smoothed_value = new_input
        else:
            self.smoothed_value = (self.alpha * new_input) + ((1 - self.alpha) * self.smoothed_value)
        return self.smoothed_value

def clamp(prev, value, minoffset, maxoffset):
    return max(prev-minoffset, min(value, prev+maxoffset))

class MoveThread(threading.Thread):
    def __init__(self, q: queue.Queue, target, margin, lower, upper):
        self.q = q
        self.target = target
        self.moving = 0
        self.offset = 4
        self.margin = margin
        self.lowlimit = lower
        self.upperlimit = upper
        i2c = busio.I2C(board.D1, board.D0)  # using i2c0
        self.POS = AnalogIn(ADS1115(i2c, mode=Mode.CONTINUOUS), P0)
        self.actual_position = prometheus_client.Gauge('actual_position', 'Actual position')
        super().__init__()
    
    def run(self):
        motors.enable()
        f = open("posdump.csv", encoding='utf-8', mode="w")
        writer = csv.writer(f)
        writer.writerow(["Target", "Raw", "offset/2.0"])
        pos = self.POS.value
        lastmove = time.monotonic()
        try:
            while True:
                # check if new target
                if not self.q.empty():
                    try: self.target = self.q.get(False)
                    except queue.Empty: pass
                    if self.target == -2: break
                # current pos
                npos = self.POS.value
                # hectic filtering (lol why am I this jank)
                if self.moving == UP:
                    writer.writerow([self.target, npos, 
                            clamp(pos, npos, -(self.offset-1), self.offset),
                        ])
                    pos = clamp(pos, npos, -(self.offset-1), self.offset)

                elif self.moving == DOWN:
                    writer.writerow([self.target, npos, 
                            clamp(pos, npos, self.offset, -(self.offset-1)),
                        ])
                    pos = clamp(pos, npos, self.offset, -(self.offset-1))
                else:
                    writer.writerow([self.target, npos, 
                            clamp(pos, npos, -(self.offset-1), -(self.offset-1)),
                        ])
                    pos = clamp(pos, npos, 5, 5)
                
                #print(self.target, round(pos), npos)
                self.actual_position.set(pos)
                if (self.moving == UP or self.moving == STOP) and pos < self.target - self.margin:
                    if self.moving == STOP and time.monotonic() - lastmove > 2: 
                        if self.moving != UP: motors.motor2.setSpeed(UPSPEED) # go up
                        self.moving = UP
                    if self.moving == DOWN: lastmove = time.monotonic()
                elif (self.moving == DOWN or self.moving == STOP) and pos > self.target + self.margin:
                    if self.moving == STOP and time.monotonic() - lastmove > 2: 
                        if self.moving != DOWN: motors.motor2.setSpeed(DOWNSPEED) # go down
                        self.moving = DOWN
                    if self.moving == DOWN: lastmove = time.monotonic()
                else: # also stop
                    if self.moving != STOP: motors.setSpeeds(0, 0)
                    self.moving = STOP
                if self.moving != 0: time.sleep(0.02)
                else: time.sleep(0.2)
            print("Exiting loop...")
        finally:
            # Stop the motors, even if there is an exception
            # or the user presses Ctrl+C to kill the process.
            motors.setSpeeds(0, 0)
            motors.disable()
            f.close


class Controller:
    def __init__(self, stats):
        self.stats = stats
        self.settings = Settings(stats)
        self.pid = self.settings.pid
        i2c = busio.I2C(board.D1, board.D0)  # using i2c0
        self.TEMP = adafruit_sht4x.SHT4x(i2c)
        self.TEMP.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION
        # PID extra options.
        self.pid.sample_time = UPDATE_RATE  # set PID update rate UPDATE_RATE
        self.pid.proportional_on_measurement = False
        self.pid.differential_on_measurement = False
        self.q = queue.Queue()
        self.mover = MoveThread(self.q, self.settings.last_position, self.settings.pos_margin, self.settings.lower, self.settings.upper)
        self.mover.start()
        self.currentsched = ""

    def checkSetSchedule(self):
        currstamp = time.strftime("%H:%M")
        sched = self.settings.fetchsched(currstamp)
        if sched:
            if sched["timestamp"] != self.currentsched:
                self.pid.setpoint = sched["temp"]
                self.settings.con.execute('''UPDATE setting SET target_temp = ? WHERE rowid=1;''', (sched["temp"],))
                self.settings.con.commit()
                self.currentsched = sched["timestamp"]

    def loop(self):
        lastupdate = time.monotonic()
        lastschedcheck = 0
        try:
            while True:
                currentupdate = time.monotonic()
                currentschedcheck = time.monotonic()
                # measure
                temp, humidity = self.TEMP.measurements
                # Do things...
                newpos = self.pid(temp)
                if newpos is not None: newpos = round(newpos)
                if self.settings.onoff:
                    self.settings.updatePostion(newpos) # store new location
                    # move to new setpoint
                    self.q.put(newpos)
                    self.settings.last_position = newpos
                # Log stats...
                self.stats.temp.set(temp)
                self.stats.humidity.set(humidity)
                # check for updated SQL values and manually move if new_pos is set...
                self.settings.update()
                if self.settings.new_pos != 0:
                    print(f"Manually moving to { self.settings.new_pos }")
                    self.q.put(self.settings.new_pos)
                    self.settings.resetNewPos()
                time.sleep(max(0.5 - (currentupdate-lastupdate), 0)) # sleep at most 0.5 secs... shouldn't be off the PID period by more than 0.5... probs...
                lastupdate = currentupdate
                if (currentschedcheck - lastschedcheck > 60):
                    self.checkSetSchedule()
                    lastschedcheck = currentschedcheck
        except KeyboardInterrupt:
            self.q.put(-2)
            print("Exiting...")
            

if __name__ == '__main__':
    # Start up the server to expose the metrics.
    prometheus_client.start_http_server(8008)
    control = Controller(Stats())
    control.loop()
