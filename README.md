Notes so I don't forget

Needed for strange system package setups: ```sudo apt install python3-venv```

```
sudo apt install pigpio
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```
pigpio for hardware PWM support.


```python3 -m venv env --system-site-packages```
System wide packages for access to the gpio module.

```~/env/bin/install requirements.txt```
