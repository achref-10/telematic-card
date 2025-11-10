#!/usr/bin/env python3
# /home/bako/battery_can.py
import can
import time
import sys
from datetime import datetime

# --- Config ---
CAN_INTERFACE = 'can0'    # interface name
BITRATE = 250000
RTR_ID = 0x18FF28F4
REQUEST_INTERVAL = 1.0    # seconds

# --- state ---
cell_voltages = [0.0] * 20
temperature_probes = [0] * 16

def open_bus():
    try:
        bus = can.interface.Bus(channel=CAN_INTERFACE, bustype='socketcan_native')
        return bus
    except Exception as e:
        print("ERROR opening CAN bus:", e)
        sys.exit(1)

def print_raw(msg):
    ts = datetime.fromtimestamp(msg.timestamp).strftime("%H:%M:%S.%f")[:-3]
    data_str = ' '.join(f"{b:02X}" for b in msg.data)
    print(f"[{ts}] RAW: 0x{msg.arbitration_id:X} [{msg.dlc}] {data_str}")

def decode_basic_info1(msg):
    print("\n--- BMS BASIC INFO 1 ---")
    status = msg.data[0]
    print(f"Cable connected: {'YES' if status & 0x01 else 'NO'}")
    print(f"Charging status: {'CHARGING' if status & 0x02 else 'NOT CHARGING'}")
    print(f"Low power: {'YES' if status & 0x04 else 'NO'}")
    print(f"Pack ready: {'READY' if status & 0x08 else 'NOT READY'}")
    soc = msg.data[1]
    print(f"SOC: {soc}%")
    current_raw = (msg.data[3] << 8) | msg.data[2]
    current = (current_raw - 5000) * 0.1
    print(f"Current: {current:.1f} A")
    voltage_raw = (msg.data[5] << 8) | msg.data[4]
    voltage = voltage_raw * 0.1
    print(f"Voltage: {voltage:.1f} V")
    fault_level = msg.data[6]
    fl = ["NO FAULT","LEVEL 1","NORMAL FAULT (50%)","FAULT WITH ALARM"]
    print(f"Fault level: {fl[fault_level] if fault_level < 4 else 'UNKNOWN'}")
    print(f"Fault code: 0x{msg.data[7]:02X}")

def decode_basic_info2(msg):
    print("\n--- BMS BASIC INFO 2 ---")
    max_cell = ((msg.data[1] << 8) | msg.data[0]) / 1000.0
    min_cell = ((msg.data[3] << 8) | msg.data[2]) / 1000.0
    print(f"Max cell: {max_cell:.3f} V, Min cell: {min_cell:.3f} V, Imbalance: {max_cell-min_cell:.3f} V")
    max_temp = msg.data[4] - 40
    min_temp = msg.data[5] - 40
    print(f"Max temp: {max_temp}°C, Min temp: {min_temp}°C")
    max_discharge = ((msg.data[7] << 8) | msg.data[6]) * 0.1
    print(f"Max discharge: {max_discharge:.1f} A")

def decode_cell_voltages(msg):
    pf = (msg.arbitration_id >> 16) & 0xFF
    base = {0xC8:0,0xC9:4,0xCA:8,0xCB:12,0xCC:16}.get(pf, -1)
    if base == -1: return
    if pf == 0xC8:
        print("\n--- CELL VOLTAGES ---")
    for i in range(0,8,2):
        idx = base + i//2
        if idx >= 19: break
        raw = (msg.data[i] << 8) | msg.data[i+1]
        v = raw / 1000.0
        cell_voltages[idx] = v
        status = "NORMAL"
        if v < 2.5 or v > 4.2: status = "CRITICAL"
        elif v < 3.0 or v > 3.8: status = "WARNING"
        print(f"Cell {idx+1:02d}: {v:.3f} V [{status}]")

def decode_temperature_info(msg):
    pf = (msg.arbitration_id >> 16) & 0xFF
    if pf != 0xB4: return
    print("\n--- TEMPERATURES ---")
    for i in range(3):
        t = msg.data[i] - 40
        temperature_probes[i] = t
        print(f"Probe {i+1}: {t}°C")

def decode_charging_demand(msg):
    print("\n--- CHARGING DEMAND ---")
    target_v = ((msg.data[1] << 8) | msg.data[0]) * 0.1
    target_i = ((msg.data[3] << 8) | msg.data[2]) * 0.1
    cmd = "START" if (msg.data[4] & 0x01) == 0 else "STOP"
    print(f"Target V: {target_v:.1f} V, Target I: {target_i:.1f} A, Cmd: {cmd}")

def decode_charger_feedback(msg):
    print("\n--- CHARGER FEEDBACK ---")
    output_v = ((msg.data[1] << 8) | msg.data[0]) * 0.1
    output_i = ((msg.data[3] << 8) | msg.data[2]) * 0.1
    print(f"Out V: {output_v:.1f} V, Out I: {output_i:.1f} A")
    if msg.dlc > 4:
        status = msg.data[4]
        flags = ["HW failure","Temp failure","Low power","Input low","Overcurrent","Charging","Comm timeout","Battery reversed"]
        for i,f in enumerate(flags):
            print(f"{f}: {'ACTIVE' if status & (1<<i) else 'normal'}")

def request_rtr(bus):
    # Create and send an RTR (remote) frame; use extended ID
    try:
        msg = can.Message(arbitration_id=RTR_ID, is_extended_id=True, is_remote_frame=True, dlc=8)
        bus.send(msg)
        print(f"Requested RTR 0x{RTR_ID:X}")
    except can.CanError as e:
        print("Failed to send RTR:", e)

def main():
    bus = open_bus()
    last_req = 0
    print("Starting loop. Press Ctrl-C to stop.")
    try:
        while True:
            now = time.time()
            if now - last_req >= REQUEST_INTERVAL:
                request_rtr(bus)
                last_req = now

            msg = bus.recv(timeout=1.0)
            if not msg:
                print("No message")
                continue

            print_raw(msg)
            cid = msg.arbitration_id
            # match IDs (use extended ID values from Arduino mapping)
            if cid == 0x98FF28F4:
                decode_basic_info1(msg)
            elif cid == 0x98FE28F4:
                decode_basic_info2(msg)
            elif cid == 0x98FFE5F4:
                decode_charging_demand(msg)
            elif cid == 0x98FF50E5:
                decode_charger_feedback(msg)
            else:
                pf = (cid >> 16) & 0xFF
                if 0xC8 <= pf <= 0xCC:
                    decode_cell_voltages(msg)
                elif 0xB4 <= pf <= 0xC6:
                    decode_temperature_info(msg)
                else:
                    print(f"Unknown CAN ID: 0x{cid:X}")

    except KeyboardInterrupt:
        print("Stopping...")

if __name__ == "__main__":
    main()
