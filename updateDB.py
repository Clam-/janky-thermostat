import sqlite3
from tempcontrolloop import SETTING_DEFAULTS, TABLE_CREATE, ROW_CREATE

DATA_GET = "SELECT * from setting;"
ROW_UPDATE = '''UPDATE setting SET pos_margin = ? WHERE rowid=1;'''
MARGIN_DEFAULT = 60
settingsfile = "settings.sqlite"

con = sqlite3.connect(settingsfile)
con.row_factory = sqlite3.Row
data = con.execute(DATA_GET)
data = SETTING_DEFAULTS | data
con.execute("DROP TABLE setting;")
con.commit()
con.execute(TABLE_CREATE)
con.commit()
con.execute(ROW_CREATE, data)
con.commit()
