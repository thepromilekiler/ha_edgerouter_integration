"""Config flow for EdgeRouter integration."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_PORT, DEFAULT_PORT
from .api import EdgeRouterAPI

_LOGGER = logging.getLogger(__name__)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EdgeRouter."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                # Validate the connection
                api = EdgeRouterAPI(
                    user_input[CONF_HOST],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    user_input.get(CONF_PORT, DEFAULT_PORT)
                )
                
                # Check connection in executor since it is blocking io
                await self.hass.async_add_executor_job(api.validate_connection)
                
                return self.async_create_entry(title=user_input[CONF_HOST], data=user_input)
                
            except Exception:
                errors["base"] = "cannot_connect"

        schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
