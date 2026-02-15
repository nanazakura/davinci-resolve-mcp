#!/usr/bin/env python3
"""
DaVinci Resolve Fusion Operations
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("davinci-resolve-mcp.fusion")


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


def get_fusion_tool_list(resolve) -> str:
    """Get a list of all tools in the current Fusion composition."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    try:
        tool_list = comp.GetToolList()
        if not tool_list:
            return "No tools found in the current composition."

        tools = []
        for idx, tool in tool_list.items():
            tool_info = {
                "index": idx,
                "name": tool.GetAttrs()["TOOLS_Name"] if tool.GetAttrs() else str(tool),
                "id": tool.GetAttrs()["TOOLS_RegID"] if tool.GetAttrs() else "Unknown",
            }
            tools.append(tool_info)

        return json.dumps({"tool_count": len(tools), "tools": tools}, indent=2)
    except Exception as e:
        return f"Error getting tool list: {str(e)}"


def add_fusion_tool(resolve, tool_id: str, name: Optional[str] = None) -> str:
    """Add a tool (node) to the current Fusion composition."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    try:
        comp.StartUndo("Add Tool: " + tool_id)

        attrs = {}
        if name:
            attrs["TOOLS_Name"] = name

        tool = comp.AddTool(tool_id, -32768, -32768)

        if not tool:
            comp.EndUndo(False)
            return f"Error: Failed to add tool '{tool_id}'. Check that the tool ID is valid."

        if name:
            tool.SetAttrs({"TOOLS_Name": name})

        tool_attrs = tool.GetAttrs()
        result = {
            "status": "success",
            "tool_name": tool_attrs.get("TOOLS_Name", str(tool)) if tool_attrs else str(tool),
            "tool_id": tool_attrs.get("TOOLS_RegID", tool_id) if tool_attrs else tool_id,
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
        output_tool = comp.FindTool(output_tool_name)
        if not output_tool:
            return f"Error: Tool '{output_tool_name}' not found in composition."

        input_tool = comp.FindTool(input_tool_name)
        if not input_tool:
            return f"Error: Tool '{input_tool_name}' not found in composition."

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


def set_fusion_tool_input(resolve, tool_name: str, input_name: str, value: str) -> str:
    """Set an input value on a Fusion tool."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    try:
        tool = comp.FindTool(tool_name)
        if not tool:
            return f"Error: Tool '{tool_name}' not found in composition."

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


def execute_fusion_script(resolve, script: str) -> str:
    """Execute a Lua script in the current Fusion composition."""
    comp, error = get_fusion_comp(resolve)
    if error:
        return error

    try:
        comp.StartUndo("Execute Script")

        comp.Execute(script)

        comp.EndUndo(True)

        # Return tool list after execution so caller can see the result
        tool_list = comp.GetToolList()
        tools = []
        if tool_list:
            for idx, tool in tool_list.items():
                tool_attrs = tool.GetAttrs()
                tools.append({
                    "name": tool_attrs.get("TOOLS_Name", str(tool)) if tool_attrs else str(tool),
                    "id": tool_attrs.get("TOOLS_RegID", "Unknown") if tool_attrs else "Unknown",
                })

        result = {
            "status": "success",
            "message": "Script executed successfully.",
            "tools_after_execution": tools,
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        try:
            comp.EndUndo(False)
        except Exception:
            pass
        return f"Error executing script: {str(e)}"
