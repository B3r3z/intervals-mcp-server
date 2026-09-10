"""
MCP tools registry for Intervals.icu MCP Server.

Handlers are re-exported here. The catalogue installs tools explicitly at startup.
"""

from intervals_mcp_server.catalogue import register_tools, tool_catalogue

# Import all tools for re-export
# Importing declarations does not install tools in a FastMCP instance.
from intervals_mcp_server.tools.activities import (  # noqa: F401
    add_activity_message,
    get_activity_messages,
    export_activity_data,
    get_activities,
    get_activity_details,
    get_activity_intervals,
    get_activity_streams,
)
from intervals_mcp_server.tools.events import (  # noqa: F401
    add_or_update_event,
    add_or_update_note,
    delete_event,
    delete_events_by_date_range,
    get_event_by_id,
    get_events,
)
from intervals_mcp_server.tools.custom_items import (  # noqa: F401
    create_custom_item,
    delete_custom_item,
    get_custom_item_by_id,
    get_custom_items,
    update_custom_item,
)
from intervals_mcp_server.tools.power_curves import (  # noqa: F401
    get_activity_power_curves,
    get_athlete_power_curves,
)
from intervals_mcp_server.tools.settings import get_sport_settings  # noqa: F401
from intervals_mcp_server.tools.metrics import get_metric_definitions  # noqa: F401
from intervals_mcp_server.tools.artifacts import get_artifact_chunk  # noqa: F401
from intervals_mcp_server.tools.session_context import get_session_context  # noqa: F401
from intervals_mcp_server.tools.analytics import (  # noqa: F401
    get_activity_best_efforts,
    get_activity_interval_stats,
    get_activity_power_hr,
)
from intervals_mcp_server.tools.quality import get_activity_data_quality  # noqa: F401
from intervals_mcp_server.tools.capabilities import get_capabilities  # noqa: F401
from intervals_mcp_server.tools.analysis_comments import (  # noqa: F401
    publish_analysis_comment,
    get_analysis_comment_status,
)
from intervals_mcp_server.tools.wellness import get_wellness_data  # noqa: F401
from intervals_mcp_server.tools.writes import apply_workout_changes, get_write_status  # noqa: F401


__all__ = ["register_tools", *tool_catalogue("admin").names()]
