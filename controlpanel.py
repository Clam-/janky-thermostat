import sqlite3
from flask import g, Flask, render_template, request, redirect, url_for

DATABASE = 'settings.sqlite'
ROW_UPDATE = "UPDATE setting SET target_temp = :target_temp, last_position = :last_position, \
  onoff = :onoff, ki = :ki, kd = :kd, kp = :kp, lower = :lower, upper = :upper, pos_margin = :pos_margin WHERE rowid=1;"
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
    return render_template('controlpanel.jinja', data=data)

@app.post('/')
def update():
    data = request.form
    con = get_db()
    con.execute(ROW_UPDATE, data)
    con.commit()
    return redirect(url_for('index'))
