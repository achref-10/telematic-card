

# Battery CAN → Firebase Telematics

This project reads CAN frames from a BMS and GPS using MCP2515 on Raspberry Pi,
decodes real values, logs them to CSV, and uploads live data to Firebase Realtime Database.

## Hardware
- Raspberry Pi
- MCP2515 CAN module (SPI)
- BMS (CAN)
- GPS (CAN)

## Features
- Real-time CAN decoding
- Non-blocking Firebase upload
- CSV logging
- BMS + GPS data parsing

## Setup

### Enable CAN
```bash
sudo ip link set can0 up type can bitrate 250000
