#!/usr/bin/env python3
"""
DaVinci Resolve Fusion Operations
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("davinci-resolve-mcp.fusion")


def _safe_get_attrs(tool):
    """Safely get tool attributes, returning empty dict on failure."""
    try:
        attrs = tool.GetAttrs()
        return attrs if attrs else {}
    except Exception:
        return {}


def _tool_name(tool):
    """Get the name of a tool safely."""
    return _safe_get_attrs(tool).get("TOOLS_Name", str(tool))


def _tool_id(tool):
    """Get the registry ID of a tool safely."""
    return _safe_get_attrs(tool).get("TOOLS_RegID", "Unknown")


def get_fusion_comp(resolve):
    """Get the current Fusion composition with error handling.

    Returns:
        tuple: (comp, error_string) - comp is None if error occurred
    """
    if resolve is None:
        return None, "Error: Not connected to DaVinci Resolve"

    fusion = resolve.Fusion()
    if not fusion:
        return None, "Error: Failed to get Fusion. Make sure DaVinci Resolve is on the Fusion page."

    comp = fusion.GetCurrentComp()
    if not comp:
        return None, "Error: No current composition. Open a Fusion composition first."

    return comp, None


def _find_tool(comp, tool_name: str):
    """Find a tool by name, returning (tool, error_string)."""
    tool = comp.FindTool(tool_name)
    if not tool:
        return None, f"Error: Tool '{tool_name}' not found in composition."
    return tool, None


def _parse_pos(pos):
    """Parse the return value of FlowView.GetPos() into (x, y).

    GetPos() may return a tuple/list, a dict-like object with numeric keys
    (Lua table), or two separate values packed in various ways.
    """
    if pos is None:
        return 0, 0
    # Tuple or list: (x, y)
    if isinstance(pos, (tuple, list)) and len(pos) >= 2:
        return float(pos[0]), float(pos[1])
    # Dict-like with 1-based or 0-based keys (Lua table mapped to Python dict)
    if isinstance(pos, dict):
        if 1 in pos and 2 in pos:
            return float(pos[1]), float(pos[2])
        if 0 in pos and 1 in pos:
            return float(pos[0]), float(pos[1])
        if "X" in pos and "Y" in pos:
            return float(pos["X"]), float(pos["Y"])
        if "x" in pos and "y" in pos:
            return float(pos["x"]), float(pos["y"])
    # Single number (shouldn't happen, but fallback)
    if isinstance(pos, (int, float)):
        return float(pos), 0
    # Last resort: try iteration
    try:
        vals = list(pos.values()) if hasattr(pos, 'values') else list(pos)
        if len(vals) >= 2:
            return float(vals[0]), float(vals[1])
    except Exception:
        pass
    return 0, 0


def _get_flow(comp):
    """Get the FlowView, returning (flow, error_string)."""
    try:
        flow = comp.CurrentFrame.FlowView
        if not flow:
            return None, "Error: Failed to get FlowView. Make sure you are on the Fusion page."
        return flow, None
    except Exception as e:
        return None, f"Error: Failed to get FlowView: {str(e)}"


# ==================== Read Operations ====================


def get_fusion_tool_list(resolve) -> str:
    """Get a list of all tools in the current Fusion composition with extended info."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    try:
        tool_list = comp.GetToolList()
        if not tool_list:
            return "No tools found in the current composition."

        flow, _ = _get_flow(comp)

        tools = []
        for idx, tool in tool_list.items():
            attrs = _safe_get_attrs(tool)
            tool_info = {
                "index": idx,
                "name": attrs.get("TOOLS_Name", str(tool)),
                "id": attrs.get("TOOLS_RegID", "Unknown"),
                "enabled": not attrs.get("TOOLB_PassThrough", False),
            }

            # Position
            if flow:
                try:
                    pos = flow.GetPos(tool)
                    x, y = _parse_pos(pos)
                    tool_info["position"] = {"x": x, "y": y}
                except Exception:
                    pass

            # Input connections
            try:
                connected_from = []
                inputs = tool.GetInputList()
                if inputs:
                    for j, inp in inputs.items():
                        connected_output = inp.GetConnectedOutput()
                        if connected_output:
                            src_tool = connected_output.GetTool()
                            if src_tool:
                                connected_from.append(_tool_name(src_tool))
                if connected_from:
                    tool_info["connected_from"] = connected_from
            except Exception:
                pass

            # Output connections
            try:
                outputs_to = []
                outputs = tool.GetOutputList()
                if outputs:
                    for j, out in outputs.items():
                        dests = out.GetConnectedInputs()
                        if dests:
                            for k, dest_inp in dests.items():
                                dest_tool = dest_inp.GetTool()
                                if dest_tool:
                                    outputs_to.append(_tool_name(dest_tool))
                if outputs_to:
                    tool_info["outputs_to"] = outputs_to
            except Exception:
                pass

            tools.append(tool_info)

        return json.dumps({"tool_count": len(tools), "tools": tools}, indent=2)
    except Exception as e:
        return f"Error getting tool list: {str(e)}"


def get_selected_tools(resolve) -> str:
    """Get a list of currently selected tools in the Fusion composition."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    try:
        selected = comp.GetToolList(True)
        if not selected:
            return json.dumps({"selected_count": 0, "tools": []}, indent=2)

        tools = []
        for i, tool in selected.items():
            tools.append({
                "name": _tool_name(tool),
                "id": _tool_id(tool),
            })

        return json.dumps({"selected_count": len(tools), "tools": tools}, indent=2)
    except Exception as e:
        return f"Error getting selected tools: {str(e)}"


def get_tool_inputs(resolve, tool_name: str) -> str:
    """Get all inputs of a Fusion tool with their current values."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    tool, error = _find_tool(comp, tool_name)
    if error:
        return error

    try:
        inputs = tool.GetInputList()
        if not inputs:
            return json.dumps({"tool": tool_name, "inputs": []}, indent=2)

        result = []
        for i, inp in inputs.items():
            attrs = inp.GetAttrs()
            if not attrs:
                continue
            entry = {
                "name": attrs.get("INPS_Name", ""),
                "id": attrs.get("INPS_ID", ""),
            }
            data_type = attrs.get("INPS_DataType")
            if data_type:
                entry["type"] = data_type

            try:
                val = inp[comp.CurrentTime]
                # Only include serializable values
                if isinstance(val, (int, float, str, bool)):
                    entry["value"] = val
                elif val is not None:
                    entry["value"] = str(val)
            except Exception:
                pass

            result.append(entry)

        return json.dumps({"tool": tool_name, "input_count": len(result), "inputs": result}, indent=2)
    except Exception as e:
        return f"Error getting tool inputs: {str(e)}"


def get_tool_outputs(resolve, tool_name: str) -> str:
    """Get all outputs of a Fusion tool."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    tool, error = _find_tool(comp, tool_name)
    if error:
        return error

    try:
        outputs = tool.GetOutputList()
        if not outputs:
            return json.dumps({"tool": tool_name, "outputs": []}, indent=2)

        result = []
        for i, out in outputs.items():
            attrs = out.GetAttrs()
            if not attrs:
                continue
            result.append({
                "name": attrs.get("OUTS_Name", ""),
                "id": attrs.get("OUTS_ID", ""),
            })

        return json.dumps({"tool": tool_name, "output_count": len(result), "outputs": result}, indent=2)
    except Exception as e:
        return f"Error getting tool outputs: {str(e)}"


def get_connections(resolve) -> str:
    """Get all node connections in the current Fusion composition."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    try:
        tools = comp.GetToolList()
        if not tools:
            return json.dumps({"connections": []}, indent=2)

        connections = []
        for i, tool in tools.items():
            inputs = tool.GetInputList()
            if not inputs:
                continue
            for j, inp in inputs.items():
                try:
                    connected = inp.GetConnectedOutput()
                    if connected:
                        src_tool = connected.GetTool()
                        if src_tool:
                            inp_attrs = inp.GetAttrs()
                            out_attrs = connected.GetAttrs()
                            connections.append({
                                "from_tool": _tool_name(src_tool),
                                "from_output": out_attrs.get("OUTS_ID", "Output") if out_attrs else "Output",
                                "to_tool": _tool_name(tool),
                                "to_input": inp_attrs.get("INPS_ID", "") if inp_attrs else "",
                            })
                except Exception:
                    continue

        return json.dumps({"connection_count": len(connections), "connections": connections}, indent=2)
    except Exception as e:
        return f"Error getting connections: {str(e)}"


def get_tool_position(resolve, tool_name: str = None) -> str:
    """Get position of a specific tool or all tools on the FlowView."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    flow, error = _get_flow(comp)
    if error:
        return error

    try:
        if tool_name:
            tool, error = _find_tool(comp, tool_name)
            if error:
                return error
            pos = flow.GetPos(tool)
            # GetPos may return a tuple, list, dict, or table-like object
            x, y = _parse_pos(pos)
            return json.dumps({"tool": tool_name, "x": x, "y": y}, indent=2)
        else:
            tools = comp.GetToolList()
            if not tools:
                return json.dumps({"positions": []}, indent=2)

            positions = []
            for i, tool in tools.items():
                pos = flow.GetPos(tool)
                x, y = _parse_pos(pos)
                positions.append({
                    "name": _tool_name(tool),
                    "x": x, "y": y,
                })
            return json.dumps({"positions": positions}, indent=2)
    except Exception as e:
        return f"Error getting tool position: {str(e)}"


# ==================== Write Operations ====================


def add_fusion_tool(resolve, tool_id: str, name: Optional[str] = None) -> str:
    """Add a tool (node) to the current Fusion composition."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    try:
        comp.StartUndo("Add Tool: " + tool_id)

        tool = comp.AddTool(tool_id, -32768, -32768)

        if not tool:
            comp.EndUndo(False)
            return f"Error: Failed to add tool '{tool_id}'. Check that the tool ID is valid."

        if name:
            tool.SetAttrs({"TOOLS_Name": name})

        result = {
            "status": "success",
            "tool_name": _tool_name(tool),
            "tool_id": _tool_id(tool),
        }

        comp.EndUndo(True)
        return json.dumps(result, indent=2)
    except Exception as e:
        try:
            comp.EndUndo(False)
        except Exception:
            pass
        return f"Error adding tool: {str(e)}"


def connect_fusion_tools(resolve, output_tool_name: str, input_tool_name: str, input_name: str = "Input") -> str:
    """Connect two tools in the Fusion composition."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    try:
        output_tool, error = _find_tool(comp, output_tool_name)
        if error:
            return error

        input_tool, error = _find_tool(comp, input_tool_name)
        if error:
            return error

        comp.StartUndo(f"Connect {output_tool_name} -> {input_tool_name}")

        input_obj = input_tool.FindMainInput(1) if input_name == "Input" else getattr(input_tool, input_name, None)
        if not input_obj:
            comp.EndUndo(False)
            return f"Error: Input '{input_name}' not found on tool '{input_tool_name}'."

        output_obj = output_tool.FindMainOutput(1)
        if not output_obj:
            comp.EndUndo(False)
            return f"Error: No main output found on tool '{output_tool_name}'."

        input_obj.ConnectTo(output_obj)

        result = {
            "status": "success",
            "connection": f"{output_tool_name} -> {input_tool_name}.{input_name}",
        }

        comp.EndUndo(True)
        return json.dumps(result, indent=2)
    except Exception as e:
        try:
            comp.EndUndo(False)
        except Exception:
            pass
        return f"Error connecting tools: {str(e)}"


def disconnect_fusion_tools(resolve, tool_name: str, input_name: str = "Input") -> str:
    """Disconnect an input on a Fusion tool."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    tool, error = _find_tool(comp, tool_name)
    if error:
        return error

    try:
        comp.StartUndo(f"Disconnect {tool_name}.{input_name}")

        inp = tool.FindMainInput(1) if input_name == "Input" else getattr(tool, input_name, None)
        if not inp:
            comp.EndUndo(False)
            return f"Error: Input '{input_name}' not found on tool '{tool_name}'."

        inp.ConnectTo()  # No argument disconnects

        comp.EndUndo(True)
        return json.dumps({"status": "success", "disconnected": f"{tool_name}.{input_name}"}, indent=2)
    except Exception as e:
        try:
            comp.EndUndo(False)
        except Exception:
            pass
        return f"Error disconnecting tools: {str(e)}"


def set_fusion_tool_input(resolve, tool_name: str, input_name: str, value: str) -> str:
    """Set an input value on a Fusion tool."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    tool, error = _find_tool(comp, tool_name)
    if error:
        return error

    try:
        # Try to convert value to appropriate type
        converted_value: Any = value
        if value.lower() == "true":
            converted_value = 1
        elif value.lower() == "false":
            converted_value = 0
        else:
            try:
                converted_value = int(value)
            except ValueError:
                try:
                    converted_value = float(value)
                except ValueError:
                    converted_value = value

        comp.StartUndo(f"Set {tool_name}.{input_name}")

        input_obj = getattr(tool, input_name, None)
        if input_obj is None:
            comp.EndUndo(False)
            return f"Error: Input '{input_name}' not found on tool '{tool_name}'."

        input_obj[comp.CurrentTime] = converted_value

        result = {
            "status": "success",
            "tool": tool_name,
            "input": input_name,
            "value": converted_value,
        }

        comp.EndUndo(True)
        return json.dumps(result, indent=2)
    except Exception as e:
        try:
            comp.EndUndo(False)
        except Exception:
            pass
        return f"Error setting input: {str(e)}"


def set_fusion_keyframe(resolve, tool_name: str, input_name: str, frame: int, value: str) -> str:
    """Set a keyframe on a Fusion tool input at a specific frame."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    tool, error = _find_tool(comp, tool_name)
    if error:
        return error

    try:
        # Convert value
        converted_value: Any = value
        if value.lower() == "true":
            converted_value = 1
        elif value.lower() == "false":
            converted_value = 0
        else:
            try:
                converted_value = int(value)
            except ValueError:
                try:
                    converted_value = float(value)
                except ValueError:
                    converted_value = value

        comp.StartUndo(f"Set Keyframe {tool_name}.{input_name} @ {frame}")

        input_obj = getattr(tool, input_name, None)
        if input_obj is None:
            comp.EndUndo(False)
            return f"Error: Input '{input_name}' not found on tool '{tool_name}'."

        input_obj[frame] = converted_value

        result = {
            "status": "success",
            "tool": tool_name,
            "input": input_name,
            "frame": frame,
            "value": converted_value,
        }

        comp.EndUndo(True)
        return json.dumps(result, indent=2)
    except Exception as e:
        try:
            comp.EndUndo(False)
        except Exception:
            pass
        return f"Error setting keyframe: {str(e)}"


def delete_fusion_tool(resolve, tool_name: str) -> str:
    """Delete a tool from the Fusion composition."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    tool, error = _find_tool(comp, tool_name)
    if error:
        return error

    try:
        comp.StartUndo(f"Delete {tool_name}")
        tool.Delete()
        comp.EndUndo(True)
        return json.dumps({"status": "success", "deleted": tool_name}, indent=2)
    except Exception as e:
        try:
            comp.EndUndo(False)
        except Exception:
            pass
        return f"Error deleting tool: {str(e)}"


def rename_fusion_tool(resolve, old_name: str, new_name: str) -> str:
    """Rename a tool in the Fusion composition."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    tool, error = _find_tool(comp, old_name)
    if error:
        return error

    try:
        comp.StartUndo(f"Rename {old_name} -> {new_name}")
        tool.SetAttrs({"TOOLS_Name": new_name})
        comp.EndUndo(True)
        return json.dumps({"status": "success", "old_name": old_name, "new_name": new_name}, indent=2)
    except Exception as e:
        try:
            comp.EndUndo(False)
        except Exception:
            pass
        return f"Error renaming tool: {str(e)}"


def enable_disable_fusion_tool(resolve, tool_name: str, enabled: bool = True) -> str:
    """Enable or disable (pass-through) a tool in the Fusion composition."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    tool, error = _find_tool(comp, tool_name)
    if error:
        return error

    try:
        comp.StartUndo(f"{'Enable' if enabled else 'Disable'} {tool_name}")
        tool.SetAttrs({"TOOLB_PassThrough": not enabled})
        comp.EndUndo(True)
        return json.dumps({"status": "success", "tool": tool_name, "enabled": enabled}, indent=2)
    except Exception as e:
        try:
            comp.EndUndo(False)
        except Exception:
            pass
        return f"Error {'enabling' if enabled else 'disabling'} tool: {str(e)}"


def copy_fusion_tool(resolve, source_name: str, new_name: str = None) -> str:
    """Copy a tool with all its settings in the Fusion composition."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    source, error = _find_tool(comp, source_name)
    if error:
        return error

    try:
        # Snapshot existing tool names before paste
        before_tools = comp.GetToolList()
        before_names = set()
        if before_tools:
            for i, t in before_tools.items():
                before_names.add(_tool_name(t))

        comp.StartUndo(f"Copy {source_name}")

        settings = source.SaveSettings()
        if not settings:
            comp.EndUndo(False)
            return f"Error: Failed to save settings from '{source_name}'."

        comp.Paste(settings)

        # Find the newly added tool by diffing tool lists
        after_tools = comp.GetToolList()
        new_tool = None
        pasted_name = None
        if after_tools:
            for i, t in after_tools.items():
                t_name = _tool_name(t)
                if t_name not in before_names:
                    new_tool = t
                    pasted_name = t_name
                    break

        if new_tool and new_name:
            new_tool.SetAttrs({"TOOLS_Name": new_name})
            pasted_name = new_name

        comp.EndUndo(True)
        return json.dumps({
            "status": "success",
            "copied_from": source_name,
            "new_tool_name": pasted_name or new_name,
        }, indent=2)
    except Exception as e:
        try:
            comp.EndUndo(False)
        except Exception:
            pass
        return f"Error copying tool: {str(e)}"


def set_tool_position(resolve, tool_name: str, x: float, y: float) -> str:
    """Set the position of a tool on the Fusion FlowView."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    tool, error = _find_tool(comp, tool_name)
    if error:
        return error

    flow, error = _get_flow(comp)
    if error:
        return error

    try:
        comp.StartUndo(f"Move {tool_name}")
        flow.SetPos(tool, x, y)
        comp.EndUndo(True)
        return json.dumps({"status": "success", "tool": tool_name, "x": x, "y": y}, indent=2)
    except Exception as e:
        try:
            comp.EndUndo(False)
        except Exception:
            pass
        return f"Error setting tool position: {str(e)}"


def auto_arrange_tools(resolve, direction: str = "horizontal", spacing: float = 2.0) -> str:
    """Auto-arrange tools in the Fusion FlowView based on connection topology."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    flow, error = _get_flow(comp)
    if error:
        return error

    try:
        tools = comp.GetToolList()
        if not tools:
            return "No tools found in the current composition."

        # Build adjacency: find root nodes (no connected inputs) and child relationships
        tool_map = {}  # name -> tool
        children = {}  # name -> [names of tools this outputs to]
        parents = {}   # name -> [names of tools that feed into this]

        for i, tool in tools.items():
            name = _tool_name(tool)
            tool_map[name] = tool
            children[name] = []
            parents[name] = []

        for i, tool in tools.items():
            name = _tool_name(tool)
            inputs = tool.GetInputList()
            if inputs:
                for j, inp in inputs.items():
                    try:
                        connected = inp.GetConnectedOutput()
                        if connected:
                            src_tool = connected.GetTool()
                            if src_tool:
                                src_name = _tool_name(src_tool)
                                if src_name in tool_map:
                                    if name not in children.get(src_name, []):
                                        children.setdefault(src_name, []).append(name)
                                    if src_name not in parents.get(name, []):
                                        parents.setdefault(name, []).append(src_name)
                    except Exception:
                        continue

        # Find root nodes (no parents)
        roots = [name for name in tool_map if not parents.get(name)]
        if not roots:
            roots = list(tool_map.keys())[:1]

        # BFS to assign layers
        visited = set()
        layers = {}  # name -> layer_index
        queue = [(r, 0) for r in roots]

        for name in roots:
            visited.add(name)

        while queue:
            name, layer = queue.pop(0)
            if name in layers:
                layers[name] = max(layers[name], layer)
            else:
                layers[name] = layer
            for child in children.get(name, []):
                if child not in visited:
                    visited.add(child)
                    queue.append((child, layer + 1))

        # Assign unvisited tools
        max_layer = max(layers.values()) if layers else 0
        for name in tool_map:
            if name not in layers:
                max_layer += 1
                layers[name] = max_layer

        # Group by layer
        layer_groups = {}
        for name, layer in layers.items():
            layer_groups.setdefault(layer, []).append(name)

        # Position
        comp.Lock()
        try:
            for layer_idx, names in sorted(layer_groups.items()):
                for pos_idx, name in enumerate(names):
                    tool = tool_map[name]
                    if direction == "horizontal":
                        flow.SetPos(tool, layer_idx * spacing, pos_idx * spacing)
                    else:
                        flow.SetPos(tool, pos_idx * spacing, layer_idx * spacing)
        finally:
            comp.Unlock()

        return json.dumps({
            "status": "success",
            "arranged_count": len(tool_map),
            "direction": direction,
            "spacing": spacing,
        }, indent=2)
    except Exception as e:
        return f"Error auto-arranging tools: {str(e)}"


def add_fusion_expression(resolve, tool_name: str, input_name: str, expression: str) -> str:
    """Set an expression on a Fusion tool input."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    tool, error = _find_tool(comp, tool_name)
    if error:
        return error

    try:
        comp.StartUndo(f"Set Expression {tool_name}.{input_name}")

        input_obj = getattr(tool, input_name, None)
        if input_obj is None:
            comp.EndUndo(False)
            return f"Error: Input '{input_name}' not found on tool '{tool_name}'."

        input_obj.SetExpression(expression)

        comp.EndUndo(True)
        return json.dumps({
            "status": "success",
            "tool": tool_name,
            "input": input_name,
            "expression": expression,
        }, indent=2)
    except Exception as e:
        try:
            comp.EndUndo(False)
        except Exception:
            pass
        return f"Error setting expression: {str(e)}"


def add_fusion_mask(resolve, target_tool: str, mask_type: str = "RectangleMask") -> str:
    """Add a mask and connect it to a tool's effect mask input."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    target, error = _find_tool(comp, target_tool)
    if error:
        return error

    try:
        comp.StartUndo(f"Add Mask to {target_tool}")

        mask = comp.AddTool(mask_type, -32768, -32768)
        if not mask:
            comp.EndUndo(False)
            return f"Error: Failed to add mask '{mask_type}'."

        target.EffectMask = mask.Output

        mask_name = _tool_name(mask)
        comp.EndUndo(True)
        return json.dumps({
            "status": "success",
            "mask_tool": mask_name,
            "mask_type": mask_type,
            "target_tool": target_tool,
        }, indent=2)
    except Exception as e:
        try:
            comp.EndUndo(False)
        except Exception:
            pass
        return f"Error adding mask: {str(e)}"


def execute_fusion_script(resolve, script: str) -> str:
    """Execute a Lua script in the current Fusion composition.

    To return data from Lua, use comp:SetData("_mcp_result", value) in your script.
    """
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    try:
        # Clear previous result
        try:
            comp.SetData("_mcp_result", None)
        except Exception:
            pass

        comp.StartUndo("Execute Script")
        comp.Execute(script)
        comp.EndUndo(True)

        # Retrieve result set by Lua script
        lua_result = None
        try:
            lua_result = comp.GetData("_mcp_result")
        except Exception:
            pass

        # Get tool list for context
        tool_list = comp.GetToolList()
        tools = []
        if tool_list:
            for idx, tool in tool_list.items():
                tools.append({
                    "name": _tool_name(tool),
                    "id": _tool_id(tool),
                })

        result = {
            "status": "success",
            "message": "Script executed successfully.",
            "result": lua_result,
            "tools_after_execution": tools,
        }
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        try:
            comp.EndUndo(False)
        except Exception:
            pass
        return f"Error executing script: {str(e)}"
