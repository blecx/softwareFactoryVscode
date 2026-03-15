#!/usr/bin/env python3
print("Starting Dev Stack Supervisor...")
print("Supervising workflow engine and agent queues...")
import time
try:
    while True:
        time.sleep(60)
except KeyboardInterrupt:
    pass
