#!/usr/bin/env python3
"""
DaVinci Resolve Edit Page Operations

Provides direct API access for Edit page timeline operations,
bypassing inspect_custom_object limitations.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("davinci-resolve-mcp.edit")


def _get_timeline(resolve):
    """Get the current timeline with full error chain. Returns (timeline, error_string)."""
    if resolve is None:
        return None, "Error: Not connected to DaVinci Resolve"

    pm = resolve.GetProjectManager()
    if not pm:
        return None, "Error: Failed to get Project Manager"

    project = pm.GetCurrentProject()
    if not project:
        return None, "Error: No project currently open"

    timeline = project.GetCurrentTimeline()
    if not timeline:
        return None, "Error: No timeline currently active"

    return timeline, None


def _get_project(resolve):
    """Get the current project. Returns (project, error_string)."""
    if resolve is None:
        return None, "Error: Not connected to DaVinci Resolve"

    pm = resolve.GetProjectManager()
    if not pm:
        return None, "Error: Failed to get Project Manager"

    project = pm.GetCurrentProject()
    if not project:
        return None, "Error: No project currently open"

    return project, None


def _get_item_by_index(timeline, track_type: str, track_index: int, item_index):
    """Get a timeline item by track/index or 'current'. Returns (item, error_string)."""
    if item_index == "current":
        item = timeline.GetCurrentVideoItem()
        if not item:
            return None, "Error: No current video item at playhead position."
        return item, None

    idx = int(item_index)
    items = timeline.GetItemListInTrack(track_type, track_index)
    if not items:
        return None, f"Error: No items found in {track_type} track {track_index}."

    # Support dict-like (1-based Lua table) or list
    if isinstance(items, dict):
        item_list = list(items.values())
    else:
        item_list = list(items)

    if idx < 0 or idx >= len(item_list):
        return None, f"Error: Item index {idx} out of range (0-{len(item_list)-1})."

    return item_list[idx], None


def _safe_val(val):
    """Convert a value to a JSON-safe type."""
    if val is None:
        return None
    if isinstance(val, (int, float, str, bool)):
        return val
    try:
        return str(val)
    except Exception:
        return None


# ==================== Timeline Info ====================


def get_current_timeline_detail(resolve) -> str:
    """Get comprehensive information about the current timeline."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    try:
        info = {
            "name": timeline.GetName(),
            "start_frame": timeline.GetStartFrame(),
            "end_frame": timeline.GetEndFrame(),
        }

        try:
            info["start_timecode"] = timeline.GetStartTimecode()
        except Exception:
            pass

        try:
            info["current_timecode"] = timeline.GetCurrentTimecode()
        except Exception:
            pass

        for track_type in ("video", "audio", "subtitle"):
            try:
                info[f"{track_type}_tracks"] = timeline.GetTrackCount(track_type)
            except Exception:
                pass

        try:
            settings = timeline.GetSetting("")
            if settings and isinstance(settings, dict):
                info["settings"] = {k: _safe_val(v) for k, v in settings.items()}
        except Exception:
            pass

        return json.dumps(info, indent=2, default=str)
    except Exception as e:
        return f"Error getting timeline info: {str(e)}"


def get_track_count(resolve, track_type: str = "video") -> str:
    """Get the number of tracks of a given type."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    try:
        count = timeline.GetTrackCount(track_type)
        return json.dumps({"track_type": track_type, "count": count}, indent=2)
    except Exception as e:
        return f"Error getting track count: {str(e)}"


# ==================== Timeline Items ====================


def get_timeline_items_detailed(resolve, track_type: str = "video", track_index: int = 1) -> str:
    """Get all items in a specific track with detailed properties."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    try:
        items = timeline.GetItemListInTrack(track_type, track_index)
        if not items:
            return json.dumps({
                "track_type": track_type,
                "track_index": track_index,
                "item_count": 0,
                "items": []
            }, indent=2)

        # Handle dict (Lua table) or list
        if isinstance(items, dict):
            item_list = list(items.values())
        else:
            item_list = list(items)

        result = []
        for i, item in enumerate(item_list):
            entry = {"index": i}
            try:
                entry["name"] = item.GetName()
            except Exception:
                entry["name"] = "Unknown"

            for method, key in [
                ("GetStart", "start"),
                ("GetEnd", "end"),
                ("GetDuration", "duration"),
                ("GetLeftOffset", "left_offset"),
                ("GetRightOffset", "right_offset"),
            ]:
                try:
                    entry[key] = getattr(item, method)()
                except Exception:
                    pass

            try:
                entry["enabled"] = item.GetClipEnabled()
            except Exception:
                pass

            try:
                entry["clip_color"] = item.GetClipColor()
            except Exception:
                pass

            try:
                uid = item.GetUniqueId()
                entry["unique_id"] = str(uid) if uid else None
            except Exception:
                pass

            try:
                entry["fusion_comp_count"] = item.GetFusionCompCount()
            except Exception:
                pass

            result.append(entry)

        return json.dumps({
            "track_type": track_type,
            "track_index": track_index,
            "item_count": len(result),
            "items": result
        }, indent=2, default=str)
    except Exception as e:
        return f"Error getting timeline items: {str(e)}"


def get_timeline_item_detail(resolve, track_type: str, track_index: int, item_index: str) -> str:
    """Get full properties of a single timeline item."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    item, error = _get_item_by_index(timeline, track_type, track_index, item_index)
    if error:
        return error

    try:
        info = {}
        info["name"] = item.GetName()

        for method, key in [
            ("GetStart", "start"),
            ("GetEnd", "end"),
            ("GetDuration", "duration"),
            ("GetSourceStartFrame", "source_start_frame"),
            ("GetSourceEndFrame", "source_end_frame"),
            ("GetLeftOffset", "left_offset"),
            ("GetRightOffset", "right_offset"),
        ]:
            try:
                info[key] = getattr(item, method)()
            except Exception:
                pass

        try:
            info["enabled"] = item.GetClipEnabled()
        except Exception:
            pass
        try:
            info["clip_color"] = item.GetClipColor()
        except Exception:
            pass
        try:
            info["unique_id"] = str(item.GetUniqueId())
        except Exception:
            pass

        try:
            flags = item.GetFlagList()
            if flags:
                info["flags"] = list(flags) if not isinstance(flags, list) else flags
        except Exception:
            pass

        try:
            markers = item.GetMarkers()
            if markers:
                info["markers"] = {str(k): _safe_val(v) for k, v in markers.items()} if isinstance(markers, dict) else str(markers)
        except Exception:
            pass

        try:
            props = item.GetProperty("")
            if props and isinstance(props, dict):
                info["properties"] = {k: _safe_val(v) for k, v in props.items()}
        except Exception:
            pass

        try:
            info["fusion_comp_count"] = item.GetFusionCompCount()
            info["fusion_comp_names"] = item.GetFusionCompNameList()
        except Exception:
            pass

        return json.dumps(info, indent=2, default=str)
    except Exception as e:
        return f"Error getting item detail: {str(e)}"


# ==================== Timeline Item Modifications ====================


def set_timeline_item_property(resolve, track_type: str, track_index: int,
                                item_index: str, property_name: str, value: str) -> str:
    """Set a property on a timeline item."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    item, error = _get_item_by_index(timeline, track_type, track_index, item_index)
    if error:
        return error

    # Convert value
    converted: Any = value
    if value.lower() == "true":
        converted = True
    elif value.lower() == "false":
        converted = False
    else:
        try:
            converted = int(value)
        except ValueError:
            try:
                converted = float(value)
            except ValueError:
                converted = value

    try:
        result = item.SetProperty(property_name, converted)
        return json.dumps({
            "status": "success" if result else "failed",
            "item": item.GetName(),
            "property": property_name,
            "value": converted,
        }, indent=2, default=str)
    except Exception as e:
        return f"Error setting property: {str(e)}"


def set_clip_color(resolve, track_type: str, track_index: int,
                   item_index: str, color: str) -> str:
    """Set the color label of a timeline clip."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    item, error = _get_item_by_index(timeline, track_type, track_index, item_index)
    if error:
        return error

    try:
        result = item.SetClipColor(color)
        return json.dumps({
            "status": "success" if result else "failed",
            "item": item.GetName(),
            "color": color,
        }, indent=2)
    except Exception as e:
        return f"Error setting clip color: {str(e)}"


def set_clip_enabled(resolve, track_type: str, track_index: int,
                     item_index: str, enabled: bool) -> str:
    """Enable or disable a timeline clip."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    item, error = _get_item_by_index(timeline, track_type, track_index, item_index)
    if error:
        return error

    try:
        result = item.SetClipEnabled(enabled)
        return json.dumps({
            "status": "success" if result else "failed",
            "item": item.GetName(),
            "enabled": enabled,
        }, indent=2)
    except Exception as e:
        return f"Error setting clip enabled: {str(e)}"


# ==================== Playhead ====================


def set_current_timecode(resolve, timecode: str) -> str:
    """Move the playhead to a specific timecode."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    try:
        result = timeline.SetCurrentTimecode(timecode)
        return json.dumps({
            "status": "success" if result else "failed",
            "timecode": timecode,
        }, indent=2)
    except Exception as e:
        return f"Error setting timecode: {str(e)}"


# ==================== Markers ====================


def get_timeline_markers(resolve) -> str:
    """Get all markers on the current timeline."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    try:
        markers = timeline.GetMarkers()
        if not markers:
            return json.dumps({"marker_count": 0, "markers": {}}, indent=2)

        # Convert to serializable format
        result = {}
        for frame, info in markers.items():
            result[str(frame)] = info if isinstance(info, dict) else _safe_val(info)

        return json.dumps({"marker_count": len(result), "markers": result}, indent=2, default=str)
    except Exception as e:
        return f"Error getting markers: {str(e)}"


def delete_timeline_marker(resolve, frame: int = None, color: str = None) -> str:
    """Delete timeline markers by frame number or color."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    if frame is None and color is None:
        return "Error: Must specify either 'frame' or 'color' to delete markers."

    try:
        if frame is not None:
            result = timeline.DeleteMarkerAtFrame(frame)
            return json.dumps({
                "status": "success" if result else "failed",
                "deleted_at_frame": frame,
            }, indent=2)
        else:
            result = timeline.DeleteMarkersByColor(color)
            return json.dumps({
                "status": "success" if result else "failed",
                "deleted_color": color,
            }, indent=2)
    except Exception as e:
        return f"Error deleting marker: {str(e)}"


# ==================== Track Operations ====================


def add_track(resolve, track_type: str) -> str:
    """Add a track to the current timeline."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    try:
        result = timeline.AddTrack(track_type)
        new_count = timeline.GetTrackCount(track_type)
        return json.dumps({
            "status": "success" if result else "failed",
            "track_type": track_type,
            "new_track_count": new_count,
        }, indent=2)
    except Exception as e:
        return f"Error adding track: {str(e)}"


def delete_track(resolve, track_type: str, track_index: int) -> str:
    """Delete a track from the current timeline."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    try:
        result = timeline.DeleteTrack(track_type, track_index)
        return json.dumps({
            "status": "success" if result else "failed",
            "track_type": track_type,
            "track_index": track_index,
        }, indent=2)
    except Exception as e:
        return f"Error deleting track: {str(e)}"


def set_track_name(resolve, track_type: str, track_index: int, name: str) -> str:
    """Set the name of a track."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    try:
        result = timeline.SetTrackName(track_type, track_index, name)
        return json.dumps({
            "status": "success" if result else "failed",
            "track_type": track_type,
            "track_index": track_index,
            "name": name,
        }, indent=2)
    except Exception as e:
        return f"Error setting track name: {str(e)}"


def set_track_lock(resolve, track_type: str, track_index: int, locked: bool) -> str:
    """Lock or unlock a track."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    try:
        result = timeline.SetTrackLock(track_type, track_index, locked)
        return json.dumps({
            "status": "success" if result else "failed",
            "track_type": track_type,
            "track_index": track_index,
            "locked": locked,
        }, indent=2)
    except Exception as e:
        return f"Error setting track lock: {str(e)}"


def set_track_enable(resolve, track_type: str, track_index: int, enabled: bool) -> str:
    """Enable or disable a track."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    try:
        result = timeline.SetTrackEnable(track_type, track_index, enabled)
        return json.dumps({
            "status": "success" if result else "failed",
            "track_type": track_type,
            "track_index": track_index,
            "enabled": enabled,
        }, indent=2)
    except Exception as e:
        return f"Error setting track enable: {str(e)}"


# ==================== Timeline Management ====================


def duplicate_timeline(resolve, new_name: str = None) -> str:
    """Duplicate the current timeline."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    try:
        new_timeline = timeline.DuplicateTimeline(new_name)
        if new_timeline:
            return json.dumps({
                "status": "success",
                "name": new_timeline.GetName() if hasattr(new_timeline, 'GetName') else new_name,
            }, indent=2)
        else:
            return json.dumps({"status": "failed"}, indent=2)
    except Exception as e:
        return f"Error duplicating timeline: {str(e)}"


def export_timeline(resolve, export_path: str, export_type: str = "AAF") -> str:
    """Export the current timeline to a file (AAF, EDL, XML, FCPXML, etc.)."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    try:
        result = timeline.Export(export_path, export_type)
        return json.dumps({
            "status": "success" if result else "failed",
            "path": export_path,
            "type": export_type,
        }, indent=2)
    except Exception as e:
        return f"Error exporting timeline: {str(e)}"


# ==================== Insert Operations ====================


def insert_fusion_title(resolve, title_name: str) -> str:
    """Insert a Fusion title into the timeline at the playhead."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    try:
        result = timeline.InsertFusionTitleIntoTimeline(title_name)
        return json.dumps({
            "status": "success" if result else "failed",
            "title": title_name,
        }, indent=2)
    except Exception as e:
        return f"Error inserting title: {str(e)}"


def insert_generator(resolve, generator_name: str) -> str:
    """Insert a generator into the timeline at the playhead."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    try:
        result = timeline.InsertGeneratorIntoTimeline(generator_name)
        return json.dumps({
            "status": "success" if result else "failed",
            "generator": generator_name,
        }, indent=2)
    except Exception as e:
        return f"Error inserting generator: {str(e)}"


# ==================== Clip AI Features ====================


def set_voice_isolation(resolve, track_type: str, track_index: int,
                        item_index: str, enabled: bool) -> str:
    """Enable or disable voice isolation on a timeline clip."""
    timeline, error = _get_timeline(resolve)
    if error:
        return error

    item, error = _get_item_by_index(timeline, track_type, track_index, item_index)
    if error:
        return error

    try:
        result = item.SetVoiceIsolationState(enabled)
        return json.dumps({
            "status": "success" if result else "failed",
            "item": item.GetName(),
            "voice_isolation": enabled,
        }, indent=2)
    except Exception as e:
        return f"Error setting voice isolation: {str(e)}"


# ==================== Media Pool ====================


def get_media_pool_clips(resolve, folder_name: str = None) -> str:
    """Get clips from the media pool, optionally from a specific folder."""
    project, error = _get_project(resolve)
    if error:
        return error

    try:
        media_pool = project.GetMediaPool()
        if not media_pool:
            return "Error: Failed to get Media Pool"

        root_folder = media_pool.GetRootFolder()
        if not root_folder:
            return "Error: Failed to get Root Folder"

        folder = None
        if folder_name:
            folder = _find_folder(root_folder, folder_name)
            if not folder:
                return f"Error: Folder '{folder_name}' not found in Media Pool."
        else:
            folder = media_pool.GetCurrentFolder()
            if not folder:
                folder = root_folder

        clips = folder.GetClipList()
        if not clips:
            return json.dumps({
                "folder": folder.GetName(),
                "clip_count": 0,
                "clips": []
            }, indent=2)

        result = []
        for clip in clips:
            if not clip:
                continue
            try:
                props = clip.GetClipProperty()
                if not props:
                    props = {}
                result.append({
                    "name": props.get("Clip Name", clip.GetName() if hasattr(clip, 'GetName') else "Unknown"),
                    "file_path": props.get("File Path", ""),
                    "duration": props.get("Duration", ""),
                    "fps": props.get("FPS", ""),
                    "resolution": props.get("Resolution", ""),
                    "video_codec": props.get("Video Codec", ""),
                    "audio_codec": props.get("Audio Codec", ""),
                })
            except Exception:
                continue

        return json.dumps({
            "folder": folder.GetName(),
            "clip_count": len(result),
            "clips": result
        }, indent=2, default=str)
    except Exception as e:
        return f"Error getting media pool clips: {str(e)}"


def get_media_pool_structure(resolve) -> str:
    """Get the folder tree structure of the media pool."""
    project, error = _get_project(resolve)
    if error:
        return error

    try:
        media_pool = project.GetMediaPool()
        if not media_pool:
            return "Error: Failed to get Media Pool"

        root_folder = media_pool.GetRootFolder()
        if not root_folder:
            return "Error: Failed to get Root Folder"

        def walk_folder(folder):
            clips = folder.GetClipList()
            clip_count = len(clips) if clips else 0
            node = {
                "name": folder.GetName(),
                "clip_count": clip_count,
                "subfolders": []
            }
            subfolders = folder.GetSubFolderList()
            if subfolders:
                for sub in subfolders:
                    if sub:
                        node["subfolders"].append(walk_folder(sub))
            return node

        tree = walk_folder(root_folder)
        return json.dumps(tree, indent=2, default=str)
    except Exception as e:
        return f"Error getting media pool structure: {str(e)}"


def _find_folder(root_folder, name: str):
    """Recursively search for a folder by name."""
    if root_folder.GetName() == name:
        return root_folder
    subfolders = root_folder.GetSubFolderList()
    if subfolders:
        for sub in subfolders:
            if sub:
                found = _find_folder(sub, name)
                if found:
                    return found
    return None
