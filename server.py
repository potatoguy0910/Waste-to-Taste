import asyncio
import random
import serial
import socket
import websockets
import aiohttp

SIMULATE = True  # Set to True for simulation mode, False for real serial data
SERIAL_PORT = 'COM7'      # Replace with your actual HC-05 COM port
BAUD_RATE = 9600
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
LAT = 21.1702  # Latitude for Surat
LON = 72.8311  # Longitude for Surat
WEATHER_UPDATE_INTERVAL = 600  # Update weather every 10 minutes (600 seconds)

ser = None
connected_clients = set()

# Map Open-Meteo weather codes to human-readable conditions
WEATHER_CODE_MAP = {
    0: "Clear", 1: "Clear", 2: "Clouds", 3: "Clouds",
    45: "Fog", 48: "Fog",
    51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
    61: "Rain", 63: "Rain", 65: "Rain",
    71: "Snow", 73: "Snow", 75: "Snow",
    80: "Rain", 81: "Rain", 82: "Rain",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm"
}

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "localhost"
    finally:
        s.close()

async def fetch_weather_data():
    async with aiohttp.ClientSession() as session:
        params = {
            "latitude": LAT,
            "longitude": LON,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        }
        try:
            async with session.get(WEATHER_API_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    current = data["current"]
                    weather_code = current["weather_code"]
                    return {
                        "temp": current["temperature_2m"],
                        "feels_like": current["temperature_2m"],  # Open-Meteo doesn't provide feels_like, use temp as fallback
                        "humidity": current["relative_humidity_2m"],
                        "condition": WEATHER_CODE_MAP.get(weather_code, "Unknown"),
                        "wind_speed": current["wind_speed_10m"]
                    }
                else:
                    print(f"Weather API error: {response.status} - {await response.text()}")
                    return None
        except Exception as e:
            print(f"Error fetching weather data: {e}")
            return None

async def serial_reader():
    loop = asyncio.get_running_loop()
    last_weather_fetch = 0
    weather_data = {
        "temp": 0,
        "feels_like": 0,
        "humidity": 0,
        "condition": "Unknown",
        "wind_speed": 0
    }

    while True:
        # Fetch weather data every 10 minutes
        current_time = asyncio.get_event_loop().time()
        if current_time - last_weather_fetch >= WEATHER_UPDATE_INTERVAL:
            fetched_weather = await fetch_weather_data()
            if fetched_weather:
                weather_data = fetched_weather
            last_weather_fetch = current_time

        if SIMULATE:
            simulated_temp = round(random.uniform(28.00, 31.00), 2)
            simulated_ph = round(random.uniform(3.0, 8.0), 2)
            combined_data = f"{simulated_temp},{simulated_ph},{weather_data['temp']},{weather_data['feels_like']},{weather_data['humidity']},{weather_data['condition']},{weather_data['wind_speed']}"
            print(f"[Simulated + Weather] {combined_data}")
            if connected_clients:
                send_tasks = [
                    asyncio.create_task(client.send(combined_data))
                    for client in connected_clients
                ]
                await asyncio.gather(*send_tasks)
            await asyncio.sleep(3)  # Send data every three seconds
        else:
            print(f"Opening serial port {SERIAL_PORT} at {BAUD_RATE} baud...")
            try:
                global ser
                ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            except serial.SerialException as e:
                print(f"Serial error: {e}")
                return

            while True:
                try:
                    data = await loop.run_in_executor(None, ser.readline)
                    data = data.decode('utf-8').strip()
                    if data:
                        combined_data = f"{data},{weather_data['temp']},{weather_data['feels_like']},{weather_data['humidity']},{weather_data['condition']},{weather_data['wind_speed']}"
                        print(f"[Serial + Weather] {combined_data}")
                        if connected_clients:
                            await asyncio.gather(*[client.send(combined_data) for client in connected_clients])
                    # Refresh weather data in non-simulation mode too
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_weather_fetch >= WEATHER_UPDATE_INTERVAL:
                        fetched_weather = await fetch_weather_data()
                        if fetched_weather:
                            weather_data = fetched_weather
                        last_weather_fetch = current_time
                except Exception as e:
                    print(f"Error reading serial: {e}")
                    await asyncio.sleep(1)

async def websocket_handler(websocket):
    print("Client connected")
    connected_clients.add(websocket)
    try:
        async for message in websocket:
            print(f"From client: {message}")
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
    print(f"WebSocket server running at ws://{local_ip}:6789")
    print("Connect your frontend using this address.")
    await websockets.serve(websocket_handler, '0.0.0.0', 6789)
    await serial_reader()

if __name__ == "__main__":
    asyncio.run(main())
