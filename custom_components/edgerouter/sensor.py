"""Sensor platform for EdgeRouter."""
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the EdgeRouter sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    uid_prefix = config_entry.entry_id

    _LOGGER.info("Setting up EdgeRouter sensors for entry: %s", uid_prefix)

    sensors = []
    
    # System Entities
    sensors.append(EdgeRouterSensor(coordinator, uid_prefix, "uptime", "Uptime", "mdi:clock-outline"))
    sensors.append(EdgeRouterSensor(coordinator, uid_prefix, "system_image", "Firmware", "mdi:chip"))
    sensors.append(EdgeRouterSensor(coordinator, uid_prefix, "errors", "Log Errors", "mdi:alert-circle", "problem"))
    sensors.append(EdgeRouterSensor(coordinator, uid_prefix, "cpu", "CPU Usage", "mdi:cpu-64-bit", None, "%"))
    sensors.append(EdgeRouterSensor(coordinator, uid_prefix, "memory", "Memory Usage", "mdi:memory", None, "%"))

    # Interface Entities
    # Interface Entities
    for iface in coordinator.data["interfaces"]:
        # Choose icon based on whether it's the Total or a specific interface
        if iface == "total":
            icon_rx = "mdi:download-network"
            icon_tx = "mdi:upload-network"
            name_suffix = "Traffic" # "EdgeRouter total Traffic Download" ? A bit weird.
            # actually helper handles names: "EdgeRouter total Download"
        else:
            icon_rx = "mdi:download"
            icon_tx = "mdi:upload"

        sensors.append(EdgeRouterInterfaceSensor(coordinator, uid_prefix, iface, "rx", icon_rx))
        sensors.append(EdgeRouterInterfaceSensor(coordinator, uid_prefix, iface, "tx", icon_tx))

    async_add_entities(sensors)

class EdgeRouterSensor(CoordinatorEntity, Entity):
    """Representation of an EdgeRouter Sensor."""

    def __init__(self, coordinator, uid_prefix, key, name, icon, device_class=None, unit_of_measurement=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._uid_prefix = uid_prefix
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
        return f"{self._uid_prefix}_{self._key}"

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

    def __init__(self, coordinator, uid_prefix, iface, direction, icon):
        """Initialize."""
        super().__init__(coordinator)
        self._uid_prefix = uid_prefix
        self._iface = iface
        self._direction = direction
        self._icon = icon

    @property
    def name(self):
        """Return the name."""
        direction_map = {"rx": "Download", "tx": "Upload"}
        friendly_dir = direction_map.get(self._direction, self._direction.upper())
        return f"EdgeRouter {self._iface} {friendly_dir}"

    @property
    def unique_id(self):
        """Return a unique ID."""
        return f"{self._uid_prefix}_{self._iface}_{self._direction}"

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
