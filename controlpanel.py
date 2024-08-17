import sqlite3
from flask import g, Flask, render_template, request, redirect, url_for
import time

DATABASE = 'settings.sqlite'
ROW_UPDATE = "UPDATE setting SET target_temp = :target_temp, last_position = :last_position, \
  onoff = :onoff, ki = :ki, kd = :kd, kp = :kp, lower = :lower, upper = :upper, pos_margin = :pos_margin, new_pos = :new_pos WHERE rowid=1;"
SCHED_INSERT = "INSERT INTO schedule VALUES(:timestamp, :temp)"
app = Flask(__name__)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.get('/')
def index():
    data = get_db().execute('''SELECT * FROM setting WHERE rowid=1;''').fetchone()
    schedule = get_db().execute('''SELECT * FROM schedule ORDER BY timestamp''').fetchall()
    return render_template('controlpanel.jinja', data=data, schedule=enumerate(schedule))

@app.post('/')
def update():
    data = request.form
    con = get_db()
    con.execute(ROW_UPDATE, data)
    con.commit()
    return redirect(url_for('index'))

def parseStamp(s):
    return time.strftime("%H:%M", time.strptime(s, "%H:%M"))

@app.post('/sched')
def updatesched():
    formdata = request.form
    stampmap = {}
    # convert form into a temp dict, and then array of named values to be inserted
    for key in formdata:
        if key.startswith("STAMP"):
            index = key[5:]
            stamp = formdata.get(key, None, type=parseStamp)
            value = formdata.get("VALUE"+index, 0, type=float)
            if stamp:
                stampmap[stamp] = value
    values = []
    for key,value in stampmap.items():
        values.append({"timestamp": key, "temp": value})
    con = get_db()
    # nuke all schedules:
    con.execute("DELETE FROM schedule;")
    # add all schedule rows
    con.executemany(SCHED_INSERT, values)
    con.commit()
    return redirect(url_for('index'))