#!/usr/bin/env bash
cd ~/janky-thermostat
~/env/bin/waitress-serve --port=8888 controlpanel:app
