# Run this at boot to continuously poll and adjust temp.
from prometheus_client import start_http_server, Gauge, Enum
from simple_pid import PID
import time
import os.path
import sqlite3

prometheus_client.REGISTRY.unregister(prometheus_client.GC_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PLATFORM_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PROCESS_COLLECTOR)

# use implied rowid
TABLE_CREATE = "CREATE TABLE setting(target_temp REAL, last_position INT, onoff INT, \
    kp REAL, ki REAL, kd REAL, lower INT, upper INT)"
ROW_CREATE = "INSERT INTO setting VALUES(:target_temp, :last_position, :onoff, :ki, :kd, :kp, :lower, :upper)"
SETTING_DEFAULTS = {
    "target_temp": 22.0,
    "last_position": 8000,
    "onoff": 1,
    "kp": -5,
    "ki": -0.01,
    "kd": -0.1,
    "lower": 1034,
    "upper": 24600
}
UPDATE_RATE = 10

# Metric reportings
class Stats:
    def __init__(self):
        self.temp = Gauge('temp', 'Temperature C')
        self.humidity = Gauge('humid', 'Humidity %')
        self.target = Gauge('target', 'Target C')
        self.position = Gauge('position', 'Valve position')
        self.onoff = Enum('onoff', 'Heating',
                states=['on', 'off'])
        self.onoff.state('on')

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

    def update(self, startup=False):
        # query SQLite
        con.execute('''SELECT * FROM setting WHERE rowid=1;''')
        data = con.fetchone()
        # load last position for init
        self.lastpos = data["last_position"]
        # update pid with new settings.
        self.pid.setpoint = data["target_temp"]
        self.pid.tunings = (data["kp"], data["ki"], data["kd"])
        self.pid.set_auto_mode(data["onoff"], data["last_position"])

    def updatePostion(self, pos):
        con.execute('''UPDATE setting SET last_position = ? WHERE rowid=1;''', pos)


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

if __name__ == '__main__':
    # Start up the server to expose the metrics.
    start_http_server(8000)
    lastpos = settings.lastpos
    while True:
        currentupdate = time.monotonic()
        # do some stuff...

        newpos = pid()
        if newpos != lastpos: settings.updatePostion(newpos) # store new location
        # move to new setpoint


        # check for updated SQL values
        settings.update()
        time.sleep(max(2 - (currentupdate-lastupdate), 0)) # sleep at most 2 secs...
        lastupdate = currentupdate
