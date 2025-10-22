"""Config flow for the Model Context Protocol integration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import logging
from typing import Any, cast

import httpx
import voluptuous as vol
from yarl import URL

from homeassistant.components.application_credentials import AuthorizationServer
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.config_entry_oauth2_flow import (
    AbstractOAuth2FlowHandler,
    async_get_implementations,
)

from . import async_get_config_entry_implementation
from .application_credentials import authorization_server_context
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_AUTHORIZATION_URL,
    CONF_SCOPE,
    CONF_TOKEN_URL,
    DOMAIN,
)
from .coordinator import TokenManager, mcp_client

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
    }
)

# OAuth server discovery endpoint for rfc8414
OAUTH_DISCOVERY_ENDPOINT = ".well-known/oauth-authorization-server"
MCP_DISCOVERY_HEADERS = {
    "MCP-Protocol-Version": "2025-03-26",
}

EXAMPLE_URL = "http://example/sse"


@dataclass
class OAuthConfig:
    """Class to hold OAuth configuration."""

    authorization_server: AuthorizationServer
    scopes: list[str] | None = None


async def async_discover_oauth_config(
    hass: HomeAssistant, mcp_server_url: str
) -> OAuthConfig:
    """Discover the OAuth configuration for the MCP server.

    This implements the functionality in the MCP spec for discovery. If the MCP server URL
    is https://api.example.com/v1/mcp, then:
    - The authorization base URL is https://api.example.com
    - The metadata endpoint MUST be at https://api.example.com/.well-known/oauth-authorization-server
    - For servers that do not implement OAuth 2.0 Authorization Server Metadata, the client uses
      default paths relative to the authorization base URL.
    """
    parsed_url = URL(mcp_server_url)
    discovery_endpoint = str(parsed_url.with_path(OAUTH_DISCOVERY_ENDPOINT))
    try:
        async with httpx.AsyncClient(headers=MCP_DISCOVERY_HEADERS) as client:
            response = await client.get(discovery_endpoint)
            response.raise_for_status()
    except httpx.TimeoutException as error:
        _LOGGER.info("Timeout connecting to MCP server: %s", error)
        raise TimeoutConnectError from error
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            _LOGGER.info("Authorization Server Metadata not found, using default paths")
            return OAuthConfig(
                authorization_server=AuthorizationServer(
                    authorize_url=str(parsed_url.with_path("/authorize")),
                    token_url=str(parsed_url.with_path("/token")),
                )
            )
        raise CannotConnect from error
    except httpx.HTTPError as error:
        _LOGGER.info("Cannot discover OAuth configuration: %s", error)
        raise CannotConnect from error

    data = response.json()
    authorize_url = data["authorization_endpoint"]
    token_url = data["token_endpoint"]
    if authorize_url.startswith("/"):
        authorize_url = str(parsed_url.with_path(authorize_url))
    if token_url.startswith("/"):
        token_url = str(parsed_url.with_path(token_url))
    # We have no way to know the minimum set of scopes needed, so request
    # all of them and let the user limit during the authorization step.
    scopes = data.get("scopes_supported")
    return OAuthConfig(
        authorization_server=AuthorizationServer(
            authorize_url=authorize_url,
            token_url=token_url,
        ),
        scopes=scopes,
    )


async def validate_input(
    hass: HomeAssistant, data: dict[str, Any], token_manager: TokenManager | None = None
) -> dict[str, Any]:
    """Validate the user input and connect to the MCP server."""
    url = data[CONF_URL]
    try:
        cv.url(url)  # Cannot be added to schema directly
    except vol.Invalid as error:
        raise InvalidUrl from error
    try:
        async with mcp_client(url, token_manager=token_manager) as session:
            response = await session.initialize()
    except httpx.TimeoutException as error:
        _LOGGER.info("Timeout connecting to MCP server: %s", error)
        raise TimeoutConnectError from error
    except httpx.HTTPStatusError as error:
        _LOGGER.info("Cannot connect to MCP server: %s", error)
        if error.response.status_code == 401:
            raise InvalidAuth from error
        raise CannotConnect from error
    except httpx.HTTPError as error:
        _LOGGER.info("Cannot connect to MCP server: %s", error)
        raise CannotConnect from error

    if not response.capabilities.tools:
        raise MissingCapabilities(
            f"MCP Server {url} does not support 'Tools' capability"
        )

    return {"title": response.serverInfo.name}


class ModelContextProtocolConfigFlow(AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Handle a config flow for Model Context Protocol."""

    VERSION = 1
    DOMAIN = DOMAIN
    logger = _LOGGER

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self.data: dict[str, Any] = {}
        self.oauth_config: OAuthConfig | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except InvalidUrl:
                errors[CONF_URL] = "invalid_url"
            except TimeoutConnectError:
                errors["base"] = "timeout_connect"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                self.data[CONF_URL] = user_input[CONF_URL]
                return await self.async_step_auth_discovery()
            except MissingCapabilities:
                return self.async_abort(reason="missing_capabilities")
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                self._async_abort_entries_match({CONF_URL: user_input[CONF_URL]})
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"example_url": EXAMPLE_URL},
        )

    async def async_step_auth_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the OAuth server discovery step.

        Since this OAuth server requires authentication, this step will attempt
        to find the OAuth medata then run the OAuth authentication flow.
        """
        try:
            oauth_config = await async_discover_oauth_config(
                self.hass, self.data[CONF_URL]
            )
        except TimeoutConnectError:
            return self.async_abort(reason="timeout_connect")
        except CannotConnect:
            return self.async_abort(reason="cannot_connect")
        except Exception:
            _LOGGER.exception("Unexpected exception")
            return self.async_abort(reason="unknown")
        else:
            _LOGGER.info("OAuth configuration: %s", oauth_config)
            self.oauth_config = oauth_config
            self.data.update(
                {
                    CONF_AUTHORIZATION_URL: oauth_config.authorization_server.authorize_url,
                    CONF_TOKEN_URL: oauth_config.authorization_server.token_url,
                    CONF_SCOPE: oauth_config.scopes,
                }
            )
            return await self.async_step_credentials_choice()

    def authorization_server(self) -> AuthorizationServer:
        """Return the authorization server provided by the MCP server."""
        return AuthorizationServer(
            self.data[CONF_AUTHORIZATION_URL],
            self.data[CONF_TOKEN_URL],
        )

    @property
    def extra_authorize_data(self) -> dict:
        """Extra data that needs to be appended to the authorize url."""
        data = {}
        if self.data and (scopes := self.data[CONF_SCOPE]) is not None:
            data[CONF_SCOPE] = " ".join(scopes)
        data.update(super().extra_authorize_data)
        return data

    async def async_step_credentials_choice(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step to ask they user if they would like to add credentials.

        This is needed since we can't automatically assume existing credentials
        should be used given they may be for another existing server.
        """
        with authorization_server_context(self.authorization_server()):
            if not await async_get_implementations(self.hass, self.DOMAIN):
                return await self.async_step_new_credentials()
            return self.async_show_menu(
                step_id="credentials_choice",
                menu_options=["pick_implementation", "new_credentials"],
            )

    async def async_step_new_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step to take the frontend flow to enter new credentials."""
        return self.async_abort(reason="missing_credentials")

    async def async_step_pick_implementation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the pick implementation step.

        This exists to dynamically set application credentials Authorization Server
        based on the values form the OAuth discovery step.
        """
        with authorization_server_context(self.authorization_server()):
            return await super().async_step_pick_implementation(user_input)

    async def async_oauth_create_entry(self, data: dict) -> ConfigFlowResult:
        """Create an entry for the flow.

        Ok to override if you want to fetch extra info or even add another step.
        """
        config_entry_data = {
            **self.data,
            **data,
        }

        async def token_manager() -> str:
            return cast(str, data[CONF_TOKEN][CONF_ACCESS_TOKEN])

        try:
            info = await validate_input(self.hass, config_entry_data, token_manager)
        except TimeoutConnectError:
            return self.async_abort(reason="timeout_connect")
        except CannotConnect:
            return self.async_abort(reason="cannot_connect")
        except MissingCapabilities:
            return self.async_abort(reason="missing_capabilities")
        except Exception:
            _LOGGER.exception("Unexpected exception")
            return self.async_abort(reason="unknown")

        # Unique id based on the application credentials OAuth Client ID
        if self.source == SOURCE_REAUTH:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data=config_entry_data
            )
        await self.async_set_unique_id(config_entry_data["auth_implementation"])
        return self.async_create_entry(
            title=info["title"],
            data=config_entry_data,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Mapping[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth dialog."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        config_entry = self._get_reauth_entry()
        self.data = {**config_entry.data}
        self.flow_impl = await async_get_config_entry_implementation(  # type: ignore[assignment]
            self.hass, config_entry
        )
        return await self.async_step_auth()


class InvalidUrl(HomeAssistantError):
    """Error to indicate the URL format is invalid."""


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class TimeoutConnectError(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class MissingCapabilities(HomeAssistantError):
    """Error to indicate that the MCP server is missing required capabilities."""
