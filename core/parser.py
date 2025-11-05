import inspect
import typing
from typing import Annotated, get_origin, get_args
from pydantic.fields import FieldInfo
from fastapi import UploadFile
from PIL import Image

def get_type_name(t):
    if t == int:
        return "integer"
    elif t == float:
        return "number"
    elif t == str:
        return "string"
    elif t == bool:
        return "boolean"
    elif t == UploadFile:
        return "file"
    
    # Check for PIL Image
    try:
        if t == Image.Image or (hasattr(t, "__name__") and t.__name__ == "Image"):
            return "file"
    except:
        pass
        
    # Handle PIL Image in executor, but for input it usually comes as UploadFile or we might handle it specifically
    # For now let's assume inputs are standard types or UploadFile
    return "string"

def parse_tool_signature(func):
    sig = inspect.signature(func)
    args = []
    
    for param_name, param in sig.parameters.items():
        if param_name == "return":
            continue
            
        arg_info = {
            "name": param_name,
            "default": None if param.default == inspect.Parameter.empty else param.default,
            "required": param.default == inspect.Parameter.empty,
            "constraints": {}
        }
        
        annotation = param.annotation
        
        # Handle Annotated (e.g. Annotated[int, Field(ge=0)])
        if get_origin(annotation) == Annotated:
            type_args = get_args(annotation)
            base_type = type_args[0]
            arg_info["type"] = get_type_name(base_type)
            
            # Look for FieldInfo or other metadata
            for metadata in type_args[1:]:
                if isinstance(metadata, FieldInfo):
                    if metadata.description:
                        arg_info["description"] = metadata.description
                    # Pydantic V2 stores constraints in metadata list
                    for constraint in metadata.metadata:
                        if hasattr(constraint, "ge"): arg_info["constraints"]["min"] = constraint.ge
                        if hasattr(constraint, "le"): arg_info["constraints"]["max"] = constraint.le
                        if hasattr(constraint, "gt"): arg_info["constraints"]["min"] = constraint.gt + 0.0001
                        if hasattr(constraint, "lt"): arg_info["constraints"]["max"] = constraint.lt - 0.0001

        else:
            arg_info["type"] = get_type_name(annotation)
            
        args.append(arg_info)
        
    return {
        "name": getattr(func, "_tool_name", func.__name__),
        "group": getattr(func, "_tool_group", "General"),
        "description": inspect.getdoc(func) or "",
        "args": args
    }
