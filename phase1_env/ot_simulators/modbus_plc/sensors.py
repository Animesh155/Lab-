"""
sensors.py — Realistic sensor models for water treatment plant PLC

Instead of pure random numbers, these sensors behave like real ones:
  - Slow drift (temperature changes gradually, not jumps)
  - Correlation (pressure depends on pump speed)
  - Noise (small Gaussian noise on top of trend)
  - Occasional faults (small chance of bad reading or alarm)

Each sensor has:
  - A current value (state)
  - An update() method called every second
  - A get_raw() method that returns the integer Modbus would expose
    (scaled appropriately so the int16 register holds it)
"""

import random
import math
import time


class Sensor:
    """Base class — every sensor knows its name, scale, range."""

    def __init__(self, name, initial, scale=10, min_val=0, max_val=65535):
        self.name = name
        self.value = float(initial)
        self.scale = scale         # multiply by this before storing in int16
        self.min_val = min_val     # physical minimum (engineering units)
        self.max_val = max_val     # physical maximum
        self.fault_active = False

    def update(self, dt=1.0):
        """Override in subclasses to evolve the value."""
        pass

    def get_raw(self):
        """Return the int16 value Modbus would store in a holding register."""
        # Clamp to physical range, apply scaling, convert to int
        clamped = max(self.min_val, min(self.max_val, self.value))
        raw = int(clamped * self.scale)
        # int16 register can hold 0-65535 (treating as unsigned)
        return max(0, min(65535, raw))


class TemperatureSensor(Sensor):
    """Slow-drifting temperature with mean reversion + noise."""

    def __init__(self, name, setpoint=20.0, scale=10, drift=0.05, noise=0.02):
        super().__init__(name, setpoint, scale, min_val=-10, max_val=150)
        self.setpoint = setpoint
        self.drift = drift          # how fast it pulls toward setpoint
        self.noise = noise           # random fluctuation per tick

    def update(self, dt=1.0):
        # Random walk
        self.value += random.gauss(0, self.noise)
        # Pull back toward setpoint (mean reversion)
        self.value += (self.setpoint - self.value) * self.drift * dt


class PressureSensor(Sensor):
    """Pressure that follows pump speed (correlation)."""

    def __init__(self, name, pump_sensor, base=30, gain=0.01, noise=0.05):
        super().__init__(name, base, scale=10, min_val=0, max_val=100)
        self.pump = pump_sensor
        self.base = base
        self.gain = gain

    def update(self, dt=1.0):
        # Pressure = base + (pump speed contribution) + noise
        if self.pump.value > 0:
            target = self.base + (self.pump.value - 1500) * self.gain
        else:
            target = self.base * 0.3  # low pressure when pump off
        # Lag — pressure doesn't change instantly
        self.value += (target - self.value) * 0.3 * dt
        self.value += random.gauss(0, 0.05)


class PumpSpeedSensor(Sensor):
    """Pump RPM — mostly stable but with small variation, can fault."""

    def __init__(self, name, setpoint=1650, scale=1, running=True):
        super().__init__(name, setpoint if running else 0, scale,
                          min_val=0, max_val=3000)
        self.setpoint = setpoint
        self.running = running

    def update(self, dt=1.0):
        if not self.running:
            self.value *= 0.9  # spin down
            if self.value < 5:
                self.value = 0
            return
        # Small random variation around setpoint
        self.value += random.gauss(0, 5)
        self.value += (self.setpoint - self.value) * 0.1


class CurrentSensor(Sensor):
    """Motor current — follows pump speed."""

    def __init__(self, name, pump_sensor, scale=100):
        super().__init__(name, 0, scale, min_val=0, max_val=50)
        self.pump = pump_sensor

    def update(self, dt=1.0):
        # Current proportional to pump speed
        if self.pump.value > 100:
            target = 6 + (self.pump.value / 1650) * 4  # ~6-10 A at full speed
        else:
            target = 0.1
        self.value += (target - self.value) * 0.4
        self.value += random.gauss(0, 0.1)


class FlowSensor(Sensor):
    """Flow rate — depends on pump speed and valve position."""

    def __init__(self, name, pump_sensor, scale=1):
        super().__init__(name, 0, scale, min_val=0, max_val=2000)
        self.pump = pump_sensor

    def update(self, dt=1.0):
        # Flow proportional to pump speed
        if self.pump.value > 100:
            target = (self.pump.value / 1650) * 1000  # ~1000 L/min nominal
        else:
            target = 0
        self.value += (target - self.value) * 0.3
        self.value += random.gauss(0, 10)


class TankLevelSensor(Sensor):
    """Tank level — slow drift between min and max."""

    def __init__(self, name, scale=10, initial=70):
        super().__init__(name, initial, scale, min_val=0, max_val=100)
        self.direction = 1   # filling or draining

    def update(self, dt=1.0):
        # Random walk with bounds
        self.value += self.direction * 0.05 + random.gauss(0, 0.1)
        if self.value > 85:
            self.direction = -1
        elif self.value < 60:
            self.direction = 1


class TurbiditySensor(Sensor):
    """Water turbidity (cloudiness) — NTU units."""

    def __init__(self, name, base=10, scale=10):
        super().__init__(name, base, scale, min_val=0, max_val=200)
        self.base = base

    def update(self, dt=1.0):
        # Small variations, occasional spikes
        self.value += random.gauss(0, 0.5)
        # Pull back to base
        self.value += (self.base - self.value) * 0.05
        # 0.5% chance of brief spike
        if random.random() < 0.005:
            self.value += random.uniform(10, 30)


class ValveSensor(Sensor):
    """Valve position 0-100%, changes slowly."""

    def __init__(self, name, scale=10, initial=50):
        super().__init__(name, initial, scale, min_val=0, max_val=100)
        self.target = initial

    def update(self, dt=1.0):
        # Slowly move toward target
        self.value += (self.target - self.value) * 0.1
        # Occasionally change target
        if random.random() < 0.01:
            self.target = random.uniform(30, 80)


class PHSensor(Sensor):
    """pH sensor — should stay near 7.0."""

    def __init__(self, name, setpoint=7.2, scale=100):
        super().__init__(name, setpoint, scale, min_val=0, max_val=14)
        self.setpoint = setpoint

    def update(self, dt=1.0):
        self.value += random.gauss(0, 0.01)
        self.value += (self.setpoint - self.value) * 0.05


class StatusSensor(Sensor):
    """PLC status: 0=running, 1=fault. Mostly 0 with rare faults."""

    def __init__(self, name):
        super().__init__(name, 0, scale=1, min_val=0, max_val=1)

    def update(self, dt=1.0):
        # 1% chance of fault, then clears next tick
        if self.value == 1:
            self.value = 0
        elif random.random() < 0.01:
            self.value = 1


class CounterSensor(Sensor):
    """Monotonically increasing counter (alarm count, cycles, etc)."""

    def __init__(self, name, scale=1):
        super().__init__(name, 0, scale, min_val=0, max_val=65535)

    def update(self, dt=1.0):
        # Increment occasionally
        if random.random() < 0.05:
            self.value += 1
            if self.value > 65000:
                self.value = 0  # wrap


# ────────────────────────────────────────────────────────────────────────
# WATER TREATMENT PLANT SENSOR LAYOUT
# ────────────────────────────────────────────────────────────────────────
# Returns a list of sensors mapped to Modbus register addresses 40001-40015
# (zero-indexed in pymodbus: addresses 0-14)
#
# Register | Name                       | Scale | Units
# 0        | intake_pump_1_speed        | 1     | RPM
# 1        | intake_pump_1_current      | 100   | Amps
# 2        | intake_pump_2_speed        | 1     | RPM (standby)
# 3        | intake_pump_2_current      | 100   | Amps
# 4        | raw_water_flow             | 1     | L/min
# 5        | raw_water_turbidity        | 10    | NTU
# 6        | intake_pressure            | 10    | PSI
# 7        | tank_level                 | 10    | %
# 8        | tank_temperature           | 10    | °C
# 9        | tank_ph                    | 100   | pH
# 10       | transfer_valve_position    | 10    | %
# 11       | transfer_flow              | 1     | L/min
# 12       | plc_status                 | 1     | 0/1
# 13       | alarm_count                | 1     | counter
# 14       | cycle_time                 | 1     | ms
# ────────────────────────────────────────────────────────────────────────

def build_sensor_array():
    """Return ordered list of 15 sensors for the water treatment PLC."""
    # Build correlated sensors (some depend on others)
    pump1 = PumpSpeedSensor("intake_pump_1_speed", setpoint=1650, running=True)
    pump2 = PumpSpeedSensor("intake_pump_2_speed", setpoint=1650, running=False)

    sensors = [
        pump1,                                                          # 0
        CurrentSensor("intake_pump_1_current", pump1),                   # 1
        pump2,                                                          # 2
        CurrentSensor("intake_pump_2_current", pump2),                   # 3
        FlowSensor("raw_water_flow", pump1),                             # 4
        TurbiditySensor("raw_water_turbidity", base=15),                 # 5
        PressureSensor("intake_pressure", pump1, base=40),               # 6
        TankLevelSensor("tank_level", initial=72),                       # 7
        TemperatureSensor("tank_temperature", setpoint=22),              # 8
        PHSensor("tank_ph", setpoint=7.2),                               # 9
        ValveSensor("transfer_valve_position", initial=55),              # 10
        FlowSensor("transfer_flow", pump1),                              # 11
        StatusSensor("plc_status"),                                       # 12
        CounterSensor("alarm_count"),                                     # 13
        Sensor("cycle_time", 10, scale=1, min_val=5, max_val=20),         # 14
    ]
    return sensors
