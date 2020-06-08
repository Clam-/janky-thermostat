import Adafruit_DHT
SENSOR = Adafruit_DHT.DHT22
PIN = 26


hum, temp = Adafruit_DHT.read_retry(SENSOR, PIN)
if humidity is not None and temperature is not None:
    print("Temp={0:0.1f}*C  Humidity={1:0.1f}%".format(temp, hum))
else:
    print("Failed...")
