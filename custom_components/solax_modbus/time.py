from .const import ATTR_MANUFACTURER, DOMAIN, CONF_MODBUS_ADDR, DEFAULT_MODBUS_ADDR
from .const import WRITE_DATA_LOCAL, WRITE_MULTISINGLE_MODBUS, WRITE_SINGLE_MODBUS
from homeassistant.components.time import PLATFORM_SCHEMA, TimeEntity
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from typing import Any, Dict, Optional
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities) -> None:
    if entry.data: # old style - remove soon
        hub_name = entry.data[CONF_NAME]
        modbus_addr = entry.data.get(CONF_MODBUS_ADDR, DEFAULT_MODBUS_ADDR)
    else:
        hub_name = entry.options[CONF_NAME] # new style
        modbus_addr = entry.options.get(CONF_MODBUS_ADDR, DEFAULT_MODBUS_ADDR) # new style
    hub = hass.data[DOMAIN][hub_name]["hub"]
    device_info = {
        "identifiers": {(DOMAIN, hub_name)},
        "name": hub.plugin.plugin_name,
        "manufacturer": hub.plugin.plugin_manufacturer,
        #"model": hub.sensor_description.inverter_model,
        "serial_number": hub.seriesnumber,
    }
    plugin = hub.plugin #getPlugin(hub_name)
    entities = []
    for time_info in plugin.TIME_TYPES:
        if plugin.matchInverterWithMask(hub._invertertype, time_info.allowedtypes, hub.seriesnumber , time_info.blacklist):
            time = SolaXModbusTime(hub_name, hub, modbus_addr, device_info, time_info)
            if time_info.write_method==WRITE_DATA_LOCAL:
                if (time_info.initvalue != None): hub.data[time_info.key] = time_info.initvalue
                hub.writeLocals[time_info.key] = time_info
                time_info.reverse_option_dict = {v: k for k, v in time_info.option_dict.items()}
            entities.append(time)

    async_add_entities(entities)
    return True

def get_payload(my_dict, search):
    for k, v in my_dict.items():
        if v == search:
            return k
    return None

class SolaXModbusTime(TimeEntity):
    """Representation of an SolaX Modbus time."""

    def __init__(self,
                 platform_name,
                 hub,
                 modbus_addr,
                 device_info,
                 time_info
    ) -> None:
        """Initialize the timeor."""
        self._platform_name = platform_name
        self._hub = hub
        self._modbus_addr = modbus_addr
        self._attr_device_info = device_info
        self._name = time_info.name
        self._key = time_info.key
        self._register = time_info.register
        self._option_dict = time_info.option_dict
        self.entity_description = time_info
        self._write_method = time_info.write_method

    async def async_added_to_hass(self):
        """Register callbacks."""
        await self._hub.async_add_solax_modbus_sensor(self._modbus_data_updated)

    async def async_will_remove_from_hass(self) -> None:
        await self._hub.async_remove_solax_modbus_sensor(self._modbus_data_updated)

    @callback
    def _modbus_data_updated(self):
        self.async_write_ha_state()

    @property
    def name(self):
        """Return the name."""
        return f"{self._platform_name} {self._name}"
    
    @property
    def native_value(self):
        """Update the current value."""
        if self.entity_description.key in self._hub.data:
            val = self._hub.data[self.entity_description.key]
            return val

    @property
    def should_poll(self) -> bool:
        """Data is delivered by the hub"""
        return False

    @property
    def unique_id(self) -> Optional[str]:
        return f"{self._platform_name}_{self._key}"

    async def async_time_option(self, value) -> None:
        """Set the time."""
        payload = get_payload(self._option_dict, value)
        if self._write_method == WRITE_MULTISINGLE_MODBUS:
            _LOGGER.info(f"writing {self._platform_name} time register {self._register} value {payload}")
            await self._hub.async_write_registers_single(unit=self._modbus_addr, address=self._register, payload=payload)
        elif self._write_method == WRITE_SINGLE_MODBUS:
            _LOGGER.info(f"writing {self._platform_name} time register {self._register} value {payload}")
            await self._hub.async_write_register(unit=self._modbus_addr, address=self._register, payload=payload)
        elif self._write_method == WRITE_DATA_LOCAL:
            _LOGGER.info(f"*** local data written {self._key}: {payload}")
            self._hub.localsUpdated = True # mark to save permanently
        self._hub.data[self._key] = value
        self.async_write_ha_state()