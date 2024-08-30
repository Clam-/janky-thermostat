from typing import Self

import sys
import csv

if len(sys.argv) != 2:
    print("Need Call file.")
    exit()

class EWMAFilter:
    def __init__(self, span):
        self.alpha = 2 / (span + 1)
        self.smoothed_value = None
    def new(self, new_input):
        if self.smoothed_value is None:
            self.smoothed_value = new_input
        else:
            self.smoothed_value = (self.alpha * new_input) + ((1 - self.alpha) * self.smoothed_value)
        return self.smoothed_value

ewma1 = EWMAFilter(span=10)
ewma2 = EWMAFilter(span=20)
nfile = sys.argv[1].split(".")
nfile = f"{nfile[0]}-new.{nfile[1]}"
with open(nfile, encoding='utf-8-sig', mode="w") as csvwfile:
    writer = csv.writer(csvwfile)
    with open(sys.argv[1], encoding='utf-8-sig') as csvfile:
        reader = csv.reader(csvfile)
        rownum = 0
        for row in reader:
            if rownum == 0: 
                row=row+[1,2]
                writer.writerow(row)
            else:
                row=row+[ewma1.new(int(row[1])), ewma2.new(int(row[1]))]
                writer.writerow(row)
            rownum += 1