#!/usr/bin/env bash
cd ~/janky-thermostat
nohup ~/env/bin/waitress-serve --port=8888 controlpanel:app >> controlpanel.log &
