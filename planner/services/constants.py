"""Game constants for calculations."""

# Conveyor belt throughput in units/min
BELT_SPEEDS = {
    1: 60,
    2: 120,
    3: 270,
    4: 480,
    5: 780,
}

# Pipe throughput in units/min
PIPE_SPEEDS = {
    1: 300,
    2: 600,
}

# Power pole connection slots
POWER_POLE_SLOTS = {
    1: 4,
    2: 6,
    3: 8,
}

PURITY_MULTIPLIERS = {
    0.5: 1.0,   # Бедное
    1.0: 2.0,   # Нормальное
    2.0: 4.0,   # Богатое
}
# Overclock exponent: power = base * (overclock ^ 1.6)
OVERCLOCK_EXPONENT = 1.321928

# Idle power fraction when building has no inputs
IDLE_POWER_FRACTION = 0.1

SOMERSLOOP_OUTPUT_MULTIPLIER = 2.0
SOMERSLOOP_POWER_MULTIPLIER = 4.0