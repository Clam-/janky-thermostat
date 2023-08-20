Notes so I don't forget

Needed for strange system package setups: ```sudo apt install python3-venv```

pigpio for hardware PWM support.
```
sudo apt install pigpio
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

env setup...
```python3 -m venv env --system-site-packages```
System wide packages for access to the gpio module.

Install requirements
```~/env/bin/install requirements.txt```

Prometheus config snippet:
```
  - job_name: "thermostat"
    static_configs:
      - targets: ["localhost:8008"]
```
