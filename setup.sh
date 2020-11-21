#!/usr/bin/env sh
rrdtool create data/temppos.rrd \
--step 60 \
DS:temp:GAUGE:120:-10:55 \
DS:pos:GAUGE:120:1000:25000 \
RRA:MAX:0.5:1:2880 \
RRA:MAX:0.5:60:730 \
RRA:MAX:0.5:240:8760
