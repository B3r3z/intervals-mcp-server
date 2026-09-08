"""
Formatting utilities for Intervals.icu MCP Server

This module contains formatting functions for handling data from the Intervals.icu API.
"""

import json
from datetime import datetime
from typing import Any


class _KeyTracker(dict):
    """A dict wrapper that records which keys are accessed."""

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__(data)
        self.accessed: set[str] = set()

    def get(self, key: str, default: Any = None) -> Any:
        self.accessed.add(key)
        return super().get(key, default)

    def __getitem__(self, key: str) -> Any:
        self.accessed.add(key)
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            self.accessed.add(key)
        return super().__contains__(key)


def format_activity_summary(activity: dict[str, Any]) -> str:
    """Format an activity into a readable string."""
    start_time = activity.get("startTime", activity.get("start_date_local", activity.get("start_date", "Unknown")))

    if isinstance(start_time, str) and len(start_time) > 10:
        # Format datetime if it's a full ISO string
        try:
            dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            start_time = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    rpe = activity.get("perceived_exertion", None)
    if rpe is None:
        rpe = activity.get("icu_rpe", "N/A")
    if isinstance(rpe, (int, float)):
        rpe = f"{rpe}/10"

    feel = activity.get("feel", "N/A")
    if isinstance(feel, int):
        feel = f"{feel}/5"

    # Gear (bike, shoes) - ICU activity payloads include the gear ID but not the
    # gear name (which lives in /athlete/{id}/gear). The tools.gear module
    # resolves the name and injects it as `_resolved_gear_name` before this
    # formatter runs. Prefer the resolved name; otherwise fall back to whatever
    # the raw payload provides (typically just an ID).
    resolved_name = activity.get("_resolved_gear_name")
    gear_raw = activity.get("gear")
    if resolved_name:
        gear_name = resolved_name
        if isinstance(gear_raw, dict):
            gear_id = gear_raw.get("id", activity.get("gear_id", "N/A"))
        else:
            gear_id = activity.get("gear_id", "N/A")
    elif isinstance(gear_raw, dict):
        gear_name = gear_raw.get("name") or gear_raw.get("display_name") or "N/A"
        gear_id = gear_raw.get("id", "N/A")
    else:
        gear_name = activity.get("gear_name", "N/A")
        gear_id = activity.get("gear_id", "N/A")

    return f"""
Activity: {activity.get("name", "Unnamed")}
ID: {activity.get("id", "N/A")}
Type: {activity.get("type", "Unknown")}
Date: {start_time}
Description: {activity.get("description", "N/A")}
Distance: {activity.get("distance", 0)} meters
Duration: {activity.get("duration", activity.get("elapsed_time", 0))} seconds
Moving Time: {activity.get("moving_time", "N/A")} seconds
Elevation Gain: {activity.get("elevationGain", activity.get("total_elevation_gain", 0))} meters
Elevation Loss: {activity.get("total_elevation_loss", "N/A")} meters

Power Data:
Average Power: {activity.get("avgPower", activity.get("icu_average_watts", activity.get("average_watts", "N/A")))} watts
Weighted Avg Power: {activity.get("icu_weighted_avg_watts", "N/A")} watts
Training Load: {activity.get("trainingLoad", activity.get("icu_training_load", "N/A"))}
FTP: {activity.get("icu_ftp", "N/A")} watts
Kilojoules: {activity.get("icu_joules", "N/A")}
Intensity: {activity.get("icu_intensity", "N/A")}
Power:HR Ratio: {activity.get("icu_power_hr", "N/A")}
Variability Index: {activity.get("icu_variability_index", "N/A")}

Heart Rate Data:
Average Heart Rate: {activity.get("avgHr", activity.get("average_heartrate", "N/A"))} bpm
Max Heart Rate: {activity.get("max_heartrate", "N/A")} bpm
LTHR: {activity.get("lthr", "N/A")} bpm
Resting HR: {activity.get("icu_resting_hr", "N/A")} bpm
Decoupling: {activity.get("decoupling", "N/A")}

Other Metrics:
Cadence: {activity.get("average_cadence", "N/A")} rpm
Calories burned: {activity.get("calories", "N/A")} kcal
Average Speed: {activity.get("average_speed", "N/A")} m/s
Max Speed: {activity.get("max_speed", "N/A")} m/s
Average Stride: {activity.get("average_stride", "N/A")}
L/R Balance: {activity.get("avg_lr_balance", "N/A")}
Weight: {activity.get("icu_weight", "N/A")} kg
RPE: {rpe}
Session RPE: {activity.get("session_rpe", "N/A")}
Feel: {feel}

Environment:
Trainer: {activity.get("trainer", "N/A")}
Average Temp: {activity.get("average_temp", "N/A")}°C
Min Temp: {activity.get("min_temp", "N/A")}°C
Max Temp: {activity.get("max_temp", "N/A")}°C
Avg Wind Speed: {activity.get("average_wind_speed", "N/A")} km/h
Headwind %: {activity.get("headwind_percent", "N/A")}%
Tailwind %: {activity.get("tailwind_percent", "N/A")}%

Training Metrics:
Fitness (CTL): {activity.get("icu_ctl", "N/A")}
Fatigue (ATL): {activity.get("icu_atl", "N/A")}
TRIMP: {activity.get("trimp", "N/A")}
Polarization Index: {activity.get("polarization_index", "N/A")}
Power Load: {activity.get("power_load", "N/A")}
HR Load: {activity.get("hr_load", "N/A")}
Pace Load: {activity.get("pace_load", "N/A")}
Efficiency Factor: {activity.get("icu_efficiency_factor", "N/A")}

Device Info:
Device: {activity.get("device_name", "N/A")}
Power Meter: {activity.get("power_meter", "N/A")}
File Type: {activity.get("file_type", "N/A")}

Gear:
Name: {gear_name}
ID: {gear_id}
"""


def format_workout(workout: dict[str, Any]) -> str:
    """Format a workout into a readable string."""
    return f"""
Workout: {workout.get("name", "Unnamed")}
Description: {workout.get("description", "No description")}
Sport: {workout.get("sport", "Unknown")}
Duration: {workout.get("duration", 0)} seconds
TSS: {workout.get("tss", "N/A")}
Intervals: {len(workout.get("intervals", []))}
"""


def _format_training_metrics(entries: dict[str, Any]) -> list[str]:
    """Format training metrics section."""
    training_metrics = []
    for k, label in [
        ("ctl", "Fitness (CTL)"),
        ("atl", "Fatigue (ATL)"),
        ("rampRate", "Ramp Rate"),
        ("ctlLoad", "CTL Load"),
        ("atlLoad", "ATL Load"),
    ]:
        if entries.get(k) is not None:
            training_metrics.append(f"- {label}: {entries[k]}")
    return training_metrics


def _format_sport_info(entries: dict[str, Any]) -> list[str]:
    """Format sport-specific info section."""
    sport_info_list = []
    if entries.get("sportInfo"):
        for sport in entries.get("sportInfo", []):
            if isinstance(sport, dict) and sport.get("eftp") is not None:
                sport_info_list.append(f"- {sport.get('type')}: eFTP = {sport['eftp']}")
    return sport_info_list


def _format_vital_signs(entries: dict[str, Any]) -> list[str]:
    """Format vital signs section."""
    vital_signs = []
    for k, label, unit in [
        ("weight", "Weight", "kg"),
        ("restingHR", "Resting HR", "bpm"),
        ("hrv", "HRV", ""),
        ("hrvSDNN", "HRV SDNN", ""),
        ("avgSleepingHR", "Average Sleeping HR", "bpm"),
        ("spO2", "SpO2", "%"),
        ("systolic", "Systolic BP", ""),
        ("diastolic", "Diastolic BP", ""),
        ("respiration", "Respiration", "breaths/min"),
        ("bloodGlucose", "Blood Glucose", "mmol/L"),
        ("lactate", "Lactate", "mmol/L"),
        ("vo2max", "VO2 Max", "ml/kg/min"),
        ("bodyFat", "Body Fat", "%"),
        ("abdomen", "Abdomen", "cm"),
        ("baevskySI", "Baevsky Stress Index", ""),
    ]:
        if entries.get(k) is not None:
            value = entries[k]
            if k == "systolic" and entries.get("diastolic") is not None:
                vital_signs.append(
                    f"- Blood Pressure: {entries['systolic']}/{entries['diastolic']} mmHg"
                )
            elif k not in ("systolic", "diastolic"):
                vital_signs.append(f"- {label}: {value}{(' ' + unit) if unit else ''}")
    return vital_signs


def _format_sleep_recovery(entries: dict[str, Any]) -> list[str]:
    """Format sleep and recovery section."""
    sleep_lines = []
    sleep_hours = None
    if entries.get("sleepSecs") is not None:
        sleep_hours = f"{entries['sleepSecs'] / 3600:.2f}"
    elif entries.get("sleepHours") is not None:
        sleep_hours = f"{entries['sleepHours']}"
    if sleep_hours is not None:
        sleep_lines.append(f"  Sleep: {sleep_hours} hours")

    if entries.get("sleepQuality") is not None:
        quality_value = entries["sleepQuality"]
        quality_labels = {1: "Great", 2: "Good", 3: "Average", 4: "Poor"}
        quality_text = quality_labels.get(quality_value, str(quality_value))
        sleep_lines.append(f"  Sleep Quality: {quality_value} ({quality_text})")

    if entries.get("sleepScore") is not None:
        sleep_lines.append(f"  Device Sleep Score: {entries['sleepScore']}/100")

    if entries.get("readiness") is not None:
        sleep_lines.append(f"  Readiness: {entries['readiness']}/10")

    return sleep_lines


def _format_menstrual_tracking(entries: dict[str, Any]) -> list[str]:
    """Format menstrual tracking section."""
    menstrual_lines = []
    if entries.get("menstrualPhase") is not None:
        menstrual_lines.append(f"  Menstrual Phase: {str(entries['menstrualPhase']).capitalize()}")
    if entries.get("menstrualPhasePredicted") is not None:
        menstrual_lines.append(
            f"  Predicted Phase: {str(entries['menstrualPhasePredicted']).capitalize()}"
        )
    return menstrual_lines


def _format_subjective_feelings(entries: dict[str, Any]) -> list[str]:
    """Format subjective feelings section."""
    subjective_lines = []
    for k, label in [
        ("soreness", "Soreness"),
        ("fatigue", "Fatigue"),
        ("stress", "Stress"),
        ("mood", "Mood"),
        ("motivation", "Motivation"),
        ("injury", "Injury Level"),
    ]:
        if entries.get(k) is not None:
            subjective_lines.append(f"  {label}: {entries[k]}/10")
    return subjective_lines


def _format_nutrition_hydration(entries: dict[str, Any]) -> list[str]:
    """Format nutrition and hydration section.

    Handles both legacy fields (kcalConsumed, hydrationVolume) and the native
    macro fields from the Intervals.icu API (carbohydrates, protein,
    fatTotal). All fields are rendered conditionally — a null/missing value
    hides the corresponding line for backward compatibility with older
    wellness records.
    """
    nutrition_lines = []
    for k, label, unit in [
        ("kcalConsumed", "Calories Consumed", ""),
        ("carbohydrates", "Carbohydrates", "g"),
        ("protein", "Protein", "g"),
        ("fatTotal", "Fat", "g"),
        ("hydrationVolume", "Hydration Volume", ""),
    ]:
        if entries.get(k) is not None:
            suffix = f" {unit}" if unit else ""
            nutrition_lines.append(f"- {label}: {entries[k]}{suffix}")

    if entries.get("hydration") is not None:
        nutrition_lines.append(f"  Hydration Score: {entries['hydration']}/10")

    return nutrition_lines


def _format_other_fields(entries: dict[str, Any], known_keys: set[str]) -> list[str]:
    """Format any fields not already handled by the standard formatting sections."""
    other_lines = []
    for key, value in entries.items():
        if key not in known_keys and value is not None:
            if isinstance(value, (dict, list)):
                other_lines.append(f"- {key}: {json.dumps(value)}")
            else:
                other_lines.append(f"- {key}: {value}")
    return other_lines


def format_wellness_entry(entries: dict[str, Any], include_all_fields: bool = False) -> str:
    """Format wellness entry data into a readable string.

    Formats various wellness metrics including training metrics, vital signs,
    sleep data, menstrual tracking, subjective feelings, nutrition, and activity.

    Args:
        entries: Dictionary containing wellness data fields such as:
            - Training metrics: ctl, atl, rampRate, ctlLoad, atlLoad
            - Vital signs: weight, restingHR, hrv, hrvSDNN, avgSleepingHR, spO2,
              systolic, diastolic, respiration, bloodGlucose, lactate, vo2max,
              bodyFat, abdomen, baevskySI
            - Sleep: sleepSecs, sleepHours, sleepQuality, sleepScore, readiness
            - Menstrual: menstrualPhase, menstrualPhasePredicted
            - Subjective: soreness, fatigue, stress, mood, motivation, injury
            - Nutrition: kcalConsumed, carbohydrates, protein, fatTotal, hydrationVolume, hydration
            - Activity: steps
            - Other: comments, locked, date
        include_all_fields: If True, any fields not covered by the standard
            sections are appended under an "Other Fields" heading (default False).

    Returns:
        A formatted string representation of the wellness entry.
    """
    if include_all_fields:
        entries = _KeyTracker(entries)
        # Mark metadata/internal keys so they don't appear in "Other Fields"
        entries.get("date")
        entries.get("updated")
        entries.get("tempWeight")
        entries.get("tempRestingHR")

    lines = ["Wellness Data:"]
    lines.append(f"Date: {entries.get('id', 'N/A')}")
    lines.append("")

    training_metrics = _format_training_metrics(entries)
    if training_metrics:
        lines.append("Training Metrics:")
        lines.extend(training_metrics)
        lines.append("")

    sport_info_list = _format_sport_info(entries)
    if sport_info_list:
        lines.append("Sport-Specific Info:")
        lines.extend(sport_info_list)
        lines.append("")

    vital_signs = _format_vital_signs(entries)
    if vital_signs:
        lines.append("Vital Signs:")
        lines.extend(vital_signs)
        lines.append("")

    sleep_lines = _format_sleep_recovery(entries)
    if sleep_lines:
        lines.append("Sleep & Recovery:")
        lines.extend(sleep_lines)
        lines.append("")

    menstrual_lines = _format_menstrual_tracking(entries)
    if menstrual_lines:
        lines.append("Menstrual Tracking:")
        lines.extend(menstrual_lines)
        lines.append("")

    subjective_lines = _format_subjective_feelings(entries)
    if subjective_lines:
        lines.append("Subjective Feelings:")
        lines.extend(subjective_lines)
        lines.append("")

    nutrition_lines = _format_nutrition_hydration(entries)
    if nutrition_lines:
        lines.append("Nutrition & Hydration:")
        lines.extend(nutrition_lines)
        lines.append("")

    if entries.get("steps") is not None:
        lines.append("Activity:")
        lines.append(f"- Steps: {entries['steps']}")
        lines.append("")

    if entries.get("comments"):
        lines.append(f"Comments: {entries['comments']}")
    if "locked" in entries:
        lines.append(f"Status: {'Locked' if entries.get('locked') else 'Unlocked'}")

    if include_all_fields and isinstance(entries, _KeyTracker):
        other_lines = _format_other_fields(entries, entries.accessed)
        if other_lines:
            lines.append("")
            lines.append("Other Fields:")
            lines.extend(other_lines)

    return "\n".join(lines)


def format_event_summary(event: dict[str, Any]) -> str:
    """Format a basic event summary into a readable string."""

    # Update to check for "date" if "start_date_local" is not provided
    event_date = event.get("start_date_local", event.get("date", "Unknown"))
    category = str(event.get("category", "")).upper()
    event_type = ("Workout" if category == "WORKOUT" or event.get("workout")
                  else "Race" if category.startswith("RACE") or event.get("race") else "Other")
    event_name = event.get("name", "Unnamed")
    event_id = event.get("id", "N/A")
    event_desc = event.get("description", "No description")

    return f"""Date: {event_date}
ID: {event_id}
Type: {event_type}
Name: {event_name}
Description: {event_desc}"""


def format_event_details(event: dict[str, Any]) -> str:
    """Format detailed event information into a readable string."""

    event_details = f"""Event Details:

ID: {event.get("id", "N/A")}
Date: {event.get("start_date_local", event.get("date", "Unknown"))}
Name: {event.get("name", "Unnamed")}
Description: {event.get("description", "No description")}"""

    # Check if it's a workout-based event
    if event.get("category") == "WORKOUT" or ("workout" in event and event["workout"]):
        workout = event.get("workout") or event
        workout_doc = event.get("workout_doc") or {}
        duration = workout.get("duration")
        if event.get("category") == "WORKOUT":
            duration = workout_doc.get("duration")
            if duration is None:
                duration = event.get("moving_time")
        duration = "N/A" if duration is None else duration
        sport = workout.get("sport", event.get("type", "Unknown"))
        intervals = workout.get("intervals")
        if event.get("category") == "WORKOUT" and isinstance(workout_doc.get("steps"), list):
            intervals = workout_doc["steps"]
        training_load = event.get("icu_training_load", workout.get("tss"))
        training_load = "N/A" if training_load is None else training_load
        event_details += f"""

Workout Information:
Workout ID: {workout.get("id", "N/A")}
Sport: {sport}
Duration: {duration} seconds
Training Load: {training_load}"""

        # Include interval count if available
        if isinstance(intervals, list):
            event_details += f"""
Intervals: {len(intervals)}"""

    # Check if it's a race
    if event.get("race") or str(event.get("category", "")).startswith("RACE"):
        event_details += f"""

Race Information:
Priority: {event.get("priority", "N/A")}
Result: {event.get("result", "N/A")}"""

    # Include calendar information
    if "calendar" in event:
        cal = event["calendar"]
        event_details += f"""

Calendar: {cal.get("name", "N/A")}"""

    return event_details


def format_activity_message(message: dict[str, Any]) -> str:
    """Format an activity message/note into a readable string."""
    created = message.get("created", "Unknown")
    if isinstance(created, str) and len(created) > 10:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            created = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    return f"""Author: {message.get("name", "Unknown")}
Date: {created}
Type: {message.get("type", "TEXT")}
Content: {message.get("content", "")}"""


def format_custom_item_details(item: dict[str, Any]) -> str:
    """Format detailed custom item information into a readable string."""
    lines = ["Custom Item Details:", ""]
    lines.append(f"ID: {item.get('id', 'N/A')}")
    lines.append(f"Name: {item.get('name', 'N/A')}")
    lines.append(f"Type: {item.get('type', 'N/A')}")

    if item.get("description"):
        lines.append(f"Description: {item['description']}")
    if item.get("visibility"):
        lines.append(f"Visibility: {item['visibility']}")
    if item.get("index") is not None:
        lines.append(f"Index: {item['index']}")
    if item.get("hide_script") is not None:
        lines.append(f"Hide Script: {item['hide_script']}")
    if item.get("content"):
        lines.append(f"Content: {json.dumps(item['content'], indent=2)}")

    return "\n".join(lines)


def format_intervals(intervals_data: dict[str, Any]) -> str:
    """Format intervals data into a readable string with all available fields.

    Args:
        intervals_data: The intervals data from the Intervals.icu API

    Returns:
        A formatted string representation of the intervals data
    """
    # Format basic intervals information
    def value(item: dict[str, Any], key: str, fallback: str = "N/A") -> Any:
        raw = item.get(key)
        return fallback if raw is None else raw

    result = f"""Intervals Analysis:

ID: {intervals_data.get("id", "N/A")}
Analyzed: {intervals_data.get("analyzed", "N/A")}

"""

    # Format individual intervals
    if "icu_intervals" in intervals_data and intervals_data["icu_intervals"]:
        result += "Individual Intervals:\n\n"

        for i, interval in enumerate(intervals_data["icu_intervals"], 1):
            result += f"""[{i}] {interval.get("label", f"Interval {i}")} ({interval.get("type", "Unknown")})
Duration: {value(interval, "elapsed_time")} seconds (moving: {value(interval, "moving_time")} seconds)
Distance: {value(interval, "distance")} meters
Start-End Indices: {value(interval, "start_index")}-{value(interval, "end_index")}

Power Metrics:
  Average Power: {value(interval, "average_watts")} watts ({value(interval, "average_watts_kg")} W/kg)
  Max Power: {value(interval, "max_watts")} watts ({value(interval, "max_watts_kg")} W/kg)
  Weighted Avg Power: {value(interval, "weighted_average_watts")} watts
  Intensity: {value(interval, "intensity")}
  Training Load: {value(interval, "training_load")}
  Joules: {value(interval, "joules")}
  Joules > FTP: {value(interval, "joules_above_ftp")}
  Power Zone: {value(interval, "zone")} ({value(interval, "zone_min_watts")}-{value(interval, "zone_max_watts")} watts)
  W' Balance: Start {value(interval, "wbal_start")}, End {value(interval, "wbal_end")}
  L/R Balance: {value(interval, "avg_lr_balance")}
  Variability: {value(interval, "w5s_variability")}
  Torque: Avg {value(interval, "average_torque")}, Min {value(interval, "min_torque")}, Max {value(interval, "max_torque")}

Heart Rate & Metabolic:
  Heart Rate: Avg {value(interval, "average_heartrate")}, Min {value(interval, "min_heartrate")}, Max {value(interval, "max_heartrate")} bpm
  Decoupling: {value(interval, "decoupling")}
  DFA α1: {value(interval, "average_dfa_a1")}
  Respiration: {value(interval, "average_respiration")} breaths/min
  EPOC: {value(interval, "average_epoc")}
  SmO2: {value(interval, "average_smo2")}% / {value(interval, "average_smo2_2")}%
  THb: {value(interval, "average_thb")} / {value(interval, "average_thb_2")}

Speed & Cadence:
  Speed: Avg {value(interval, "average_speed")}, Min {value(interval, "min_speed")}, Max {value(interval, "max_speed")} m/s
  GAP: {value(interval, "gap")} m/s
  Cadence: Avg {value(interval, "average_cadence")}, Min {value(interval, "min_cadence")}, Max {value(interval, "max_cadence")} rpm
  Stride: {value(interval, "average_stride")}

Elevation & Environment:
  Elevation Gain: {value(interval, "total_elevation_gain")} meters
  Altitude: Min {value(interval, "min_altitude")}, Max {value(interval, "max_altitude")} meters
  Gradient: {value(interval, "average_gradient")}%
  Temperature: {value(interval, "average_temp")}°C (Weather: {value(interval, "average_weather_temp")}°C, Feels like: {value(interval, "average_feels_like")}°C)
  Wind: Speed {value(interval, "average_wind_speed")} km/h, Gust {value(interval, "average_wind_gust")} km/h, Direction {value(interval, "prevailing_wind_deg")}°
  Headwind: {value(interval, "headwind_percent")}%, Tailwind: {value(interval, "tailwind_percent")}%

"""

    # Format interval groups
    if "icu_groups" in intervals_data and intervals_data["icu_groups"]:
        result += "Interval Groups:\n\n"

        for i, group in enumerate(intervals_data["icu_groups"], 1):
            result += f"""Group: {group.get("id", f"Group {i}")} (Contains {value(group, "count")} intervals)
Duration: {value(group, "elapsed_time")} seconds (moving: {value(group, "moving_time")} seconds)
Distance: {value(group, "distance")} meters
Start-End Indices: {value(group, "start_index")}-N/A

Power: Avg {value(group, "average_watts")} watts ({value(group, "average_watts_kg")} W/kg), Max {value(group, "max_watts")} watts
W. Avg Power: {value(group, "weighted_average_watts")} watts, Intensity: {value(group, "intensity")}
Heart Rate: Avg {value(group, "average_heartrate")}, Max {value(group, "max_heartrate")} bpm
Speed: Avg {value(group, "average_speed")}, Max {value(group, "max_speed")} m/s
Cadence: Avg {value(group, "average_cadence")}, Max {value(group, "max_cadence")} rpm

"""

    return result


def _format_duration_label(secs: int) -> str:
    """Format seconds into a concise human-readable label (e.g. 5s, 2m, 1h)."""
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        mins = secs // 60
        remainder = secs % 60
        if remainder:
            return f"{mins}m{remainder}s"
        return f"{mins}m"
    hours = secs // 3600
    remainder = (secs % 3600) // 60
    if remainder:
        return f"{hours}h{remainder}m"
    return f"{hours}h"


def format_power_curves(
    curves: list[dict[str, Any]],
    activity_type: str,
    include_normalised: bool,
) -> str:
    """Format extracted power curve data into a concise readable string.

    Args:
        curves: List of extracted curve data dicts with id, label, data_points.
        activity_type: The activity type used for the query.
        include_normalised: Whether W/kg data is included.

    Returns:
        A formatted string representation of the power curves.
    """
    lines: list[str] = [f"Power Curves ({activity_type}):", ""]

    for curve in curves:
        label = curve.get("label", curve.get("id", "Unknown"))
        start = curve.get("start", "")
        end = curve.get("end", "")
        date_range = ""
        if start and end:
            # Trim time portion if present
            start_short = start[:10] if len(start) > 10 else start
            end_short = end[:10] if len(end) > 10 else end
            date_range = f" ({start_short} to {end_short})"

        lines.append(f"{label}{date_range}:")

        data_points = curve.get("data_points", [])
        if not data_points:
            lines.append("  No data available for requested durations.")
            lines.append("")
            continue

        for point in data_points:
            dur_label = _format_duration_label(point["secs"])
            watts = point.get("watts")
            aid = point.get("activity_id", "")
            parts = [f"  {dur_label}: {watts}W"]
            if include_normalised and "watts_per_kg" in point:
                parts.append(f"{point['watts_per_kg']:.2f}W/kg")
                wkg_aid = point.get("wkg_activity_id", "")
                if wkg_aid and wkg_aid != aid:
                    parts.append(f"[{aid}|wkg:{wkg_aid}]")
                else:
                    parts.append(f"[{aid}]")
            else:
                parts.append(f"[{aid}]")
            lines.append(" ".join(parts))
        lines.append("")

    return "\n".join(lines)
