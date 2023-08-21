import sqlite3

ROW_ADD = "ALTER TABLE setting ADD COLUMN pos_margin REAL;"
ROW_UPDATE = '''UPDATE setting SET pos_margin = ? WHERE rowid=1;'''
MARGIN_DEFAULT = 50.0
settingsfile = "settings.sqlite"
con = sqlite3.connect(settingsfile)
con.execute(ROW_ADD)
con.commit()
self.con.execute(ROW_UPDATE, (MARGIN_DEFAULT,))
con.commit()
