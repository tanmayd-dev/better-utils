from typing import Callable, Optional
from functools import wraps

def tool(name: Optional[str] = None, group: Optional[str] = None):
    """
    Decorator to register a function as a tool.
    
    Args:
        name: The display name of the tool. If None, uses the function name.
        group: The category/group for the tool. If None, inferred from directory.
    """
    def decorator(func: Callable):
        # Attach metadata to the function object itself
        # This will be read by the registry later
        func._is_tool = True
        func._tool_name = name
        func._tool_group = group
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator
