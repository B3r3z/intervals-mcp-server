"""
Intervals.icu MCP Server

This module implements a Model Context Protocol (MCP) server for connecting
Claude with the Intervals.icu API. It provides tools for retrieving and managing
athlete data, including activities, events, workouts, and wellness metrics.

Main Features:
    - Activity retrieval and detailed analysis
    - Event management (races, workouts, calendar items)
    - Wellness data tracking and visualization
    - Error handling with user-friendly messages
    - Configurable parameters with environment variable support

Usage:
    This server is designed to be run as a standalone script and exposes several MCP tools
    for use with Claude Desktop or other MCP-compatible clients. The server loads configuration
    from environment variables (optionally via a .env file) and communicates with the Intervals.icu API.

    To run the server:
        $ python src/intervals_mcp_server/server.py

    The installed tools and their access modes are described by get_capabilities,
    using the same catalogue that startup registers with FastMCP.

    See the README for more details on configuration and usage.
"""

import logging

from intervals_mcp_server.catalogue import register_tools, tool_catalogue

# Import API client and configuration
from intervals_mcp_server.api.client import (
    make_intervals_request,
)
from intervals_mcp_server.config import get_config
from intervals_mcp_server.mcp_instance import mcp

# Import types and validation
from intervals_mcp_server.server_setup import setup_transport, start_server
from intervals_mcp_server.utils.validation import validate_athlete_id

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("intervals_icu_mcp_server")

# Get configuration instance
config = get_config()

# Import handlers for compatibility; installation is explicit below.
# Import tool functions for re-export
from intervals_mcp_server.tools.activities import (  # pylint: disable=wrong-import-position  # noqa: E402
    add_activity_message as add_activity_message,
    get_activities as get_activities,
    get_activity_details as get_activity_details,
    get_activity_intervals as get_activity_intervals,
    get_activity_messages as get_activity_messages,
    get_activity_streams as get_activity_streams,
    export_activity_data as export_activity_data,
)
from intervals_mcp_server.tools.events import (  # pylint: disable=wrong-import-position  # noqa: E402
    add_or_update_event as add_or_update_event,
    add_or_update_note as add_or_update_note,
    delete_event as delete_event,
    delete_events_by_date_range as delete_events_by_date_range,
    get_event_by_id as get_event_by_id,
    get_events as get_events,
)
from intervals_mcp_server.tools.wellness import get_wellness_data as get_wellness_data  # pylint: disable=wrong-import-position  # noqa: E402
from intervals_mcp_server.tools.power_curves import (  # pylint: disable=wrong-import-position  # noqa: E402
    get_activity_power_curves as get_activity_power_curves,
    get_athlete_power_curves as get_athlete_power_curves,
)
from intervals_mcp_server.tools.settings import get_sport_settings as get_sport_settings  # pylint: disable=wrong-import-position  # noqa: E402
from intervals_mcp_server.tools.metrics import get_metric_definitions as get_metric_definitions  # pylint: disable=wrong-import-position  # noqa: E402
from intervals_mcp_server.tools.analytics import (  # pylint: disable=wrong-import-position  # noqa: E402
    get_activity_best_efforts as get_activity_best_efforts,
    get_activity_interval_stats as get_activity_interval_stats,
)
from intervals_mcp_server.tools.capabilities import get_capabilities as get_capabilities  # pylint: disable=wrong-import-position  # noqa: E402
from intervals_mcp_server.tools.artifacts import get_artifact_chunk as get_artifact_chunk  # pylint: disable=wrong-import-position  # noqa: E402
from intervals_mcp_server.tools.session_context import get_session_context as get_session_context  # pylint: disable=wrong-import-position  # noqa: E402
from intervals_mcp_server.tools.writes import (  # pylint: disable=wrong-import-position  # noqa: E402
    apply_workout_changes as apply_workout_changes,
    get_write_status as get_write_status,
)
from intervals_mcp_server.tools.analysis_comments import (  # noqa: E402
    publish_analysis_comment as publish_analysis_comment,
    get_analysis_comment_status as get_analysis_comment_status,
)
from intervals_mcp_server.tools.custom_items import (  # pylint: disable=wrong-import-position  # noqa: E402
    create_custom_item as create_custom_item,
    delete_custom_item as delete_custom_item,
    get_custom_item_by_id as get_custom_item_by_id,
    get_custom_items as get_custom_items,
    update_custom_item as update_custom_item,
)


# One catalogue supplies installation, availability and capabilities.
catalogue = register_tools(mcp)
__all__ = ["make_intervals_request", *tool_catalogue("admin").names()]


# Run the server
if __name__ == "__main__":
    # Validate ATHLETE_ID when server starts (not at import time to allow tests)
    validate_athlete_id(config.athlete_id)

    # Setup transport and start server
    selected_transport = setup_transport()
    start_server(mcp, selected_transport)
