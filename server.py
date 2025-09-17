import asyncio
import random
import websockets
import socket
import serial

SIMULATE = True  # Set to True for simulation mode, False for real serial data
SERIAL_PORT = 'COM3'  # Replace with your actual serial port (e.g., '/dev/ttyUSB0' on Linux/Mac)
BAUD_RATE = 9600  # Should match your Arduino setup

ser = None
connected_clients = set()

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # This connects to an external address to get local IP without sending data
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "localhost"
    finally:
        s.close()

async def serial_reader():
    global ser
    loop = asyncio.get_running_loop()
    if SIMULATE:
        print("Running in simulation mode...")
        while True:
            simulated_temp = round(random.uniform(28.00, 31.00), 2)
            simulated_ph = round(random.uniform(4.0, 9.0), 2)
            simulated_data = f"{simulated_temp},{simulated_ph}"
            print(f"Sending: {simulated_data}")
            if connected_clients:
                send_tasks = [
                    asyncio.create_task(client.send(simulated_data))
                    for client in connected_clients
                ]
                await asyncio.gather(*send_tasks)
            await asyncio.sleep(3)  # Send data every three second
    else:
        print(f"Opening serial port {SERIAL_PORT} at {BAUD_RATE} baud...")
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=None)  # Blocking readline
        while True:
            try:
                data = await loop.run_in_executor(None, ser.readline)
                data = data.decode('utf-8').strip()
                if data:
                    print(f"Received from serial: {data}")
                    if connected_clients:
                        send_tasks = [
                            asyncio.create_task(client.send(data))
                            for client in connected_clients
                        ]
                        await asyncio.gather(*send_tasks)
            except Exception as e:
                print(f"Serial read error: {e}")
                await asyncio.sleep(1)  # Retry after delay

async def websocket_handler(websocket):
    global ser
    print("Client connected")
    connected_clients.add(websocket)
    try:
        async for message in websocket:
            print(f"Received from client: {message}")
            if message in ('ON', 'OFF'):
                if SIMULATE:
                    print(f"Simulating send to serial: {message}")
                else:
                    if ser:
                        await asyncio.get_running_loop().run_in_executor(None, ser.write, (message + '\n').encode('utf-8'))
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        print("Client disconnected")
        connected_clients.remove(websocket)

async def main():
    local_ip = get_local_ip()
    websocket_server = await websockets.serve(websocket_handler, '0.0.0.0', 6789)
    print(f"WebSocket server started at ws://{local_ip}:6789")
    print("Update the WebSocket URL in your HTML to match this address, e.g., 'ws://YOUR_IP:6789/'")

    await serial_reader()

asyncio.run(main())