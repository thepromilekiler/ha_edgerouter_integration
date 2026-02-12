"""Sensor platform for EdgeRouter."""
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the EdgeRouter sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensors = []
    
    # System Entities
    sensors.append(EdgeRouterSensor(coordinator, "uptime", "Uptime", "mdi:clock-outline"))
    sensors.append(EdgeRouterSensor(coordinator, "system_image", "Firmware", "mdi:chip"))
    sensors.append(EdgeRouterSensor(coordinator, "errors", "Log Errors", "mdi:alert-circle", "problem"))
    sensors.append(EdgeRouterSensor(coordinator, "cpu", "CPU Usage", "mdi:cpu-64-bit", None, "%"))
    sensors.append(EdgeRouterSensor(coordinator, "memory", "Memory Usage", "mdi:memory", None, "%"))

    # Interface Entities
    for iface in coordinator.data["interfaces"]:
        sensors.append(EdgeRouterInterfaceSensor(coordinator, iface, "rx", "mdi:download"))
        sensors.append(EdgeRouterInterfaceSensor(coordinator, iface, "tx", "mdi:upload"))

    async_add_entities(sensors)


class EdgeRouterSensor(CoordinatorEntity, Entity):
    """Representation of an EdgeRouter Sensor."""

    def __init__(self, coordinator, key, name, icon, device_class=None, unit_of_measurement=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._name = name
        self._icon = icon
        self._device_class = device_class
        self._unit_of_measurement = unit_of_measurement

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"EdgeRouter {self._name}"

    @property
    def unique_id(self):
        """Return a unique ID."""
        return f"{self.coordinator.data.get('system_image')}_{self._key}"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get(self._key)

    @property
    def icon(self):
        """Return the icon."""
        return self._icon

    @property
    def device_class(self):
        return self._device_class

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement


class EdgeRouterInterfaceSensor(CoordinatorEntity, Entity):
    """Representation of an EdgeRouter Interface Traffic Sensor."""

    def __init__(self, coordinator, iface, direction, icon):
        """Initialize."""
        super().__init__(coordinator)
        self._iface = iface
        self._direction = direction
        self._icon = icon

    @property
    def name(self):
        """Return the name."""
        return f"EdgeRouter {self._iface} {self._direction.upper()}"

    @property
    def unique_id(self):
        """Return a unique ID."""
        # Ideally use MAC address, but we use system_image+iface+direction as a poor man's unique ID for now
        # ensuring it persists across reboots (unless firmware changes, which is a known limitation of this lazy ID approach)
        # A better approach requires fetching MAC or Serial in api.py
        return f"{self.coordinator.data.get('system_image')}_{self._iface}_{self._direction}"

    @property
    def state(self):
        """Return the state."""
        try:
            val = self.coordinator.data["interfaces"][self._iface][self._direction]
            return f"{val:.2f}"
        except KeyError:
            return None

    @property
    def unit_of_measurement(self):
        """Return the unit."""
        return "Mbps"

    @property
    def icon(self):
        """Return the icon."""
        return self._icon
