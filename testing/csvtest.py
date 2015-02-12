#!/usr/bin/env python

import csv

with open("test.csv", "wb") as outfile:
    with open("in.txt", "r") as infile:
        writer = csv.writer(outfile)
        for line in infile:
            writer.writerow(["Row",line])
    writer.writerow(['Spam', 'Unicode Spam'])
    writer.writerow([""" Test """, """ Test, with comma """, """ "Test" """, """ Test, with "comma" """, ])
