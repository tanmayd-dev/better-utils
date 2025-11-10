import os
import importlib.util
import sys
import traceback
from pathlib import Path
from .parser import parse_tool_signature

class ToolRegistry:
    def __init__(self, tools_dir: str):
        self.tools_dir = Path(tools_dir)
        self.tools = {} # id -> {func, schema, path}
        self.modules = {} # path -> module
        
    def load_tools(self):
        self.tools = {}
        print(f"Scanning for tools in {self.tools_dir}...")
        
        if not self.tools_dir.exists():
            os.makedirs(self.tools_dir)
            
        for file_path in self.tools_dir.rglob("*.py"):
            if file_path.name.startswith("__") or "tests" in file_path.parts:
                continue
            self.load_module(file_path)
            
    def load_module(self, file_path: Path):
        module_name = f"tools.{file_path.stem}"
        
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if not spec or not spec.loader:
                return
                
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            self.modules[str(file_path)] = module
            
            # Scan for decorated functions
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if callable(attr) and getattr(attr, "_is_tool", False):
                    tool_id = f"{file_path.stem}_{attr_name}"
                    
                    # Infer group from folder structure if not set
                    # Always infer group from folder structure
                    rel_path = file_path.relative_to(self.tools_dir)
                    if len(rel_path.parts) > 1:
                        attr._tool_group = rel_path.parts[0].capitalize()
                    else:
                        attr._tool_group = "General"
                            
                    schema = parse_tool_signature(attr)
                    schema["id"] = tool_id
                    
                    self.tools[tool_id] = {
                        "func": attr,
                        "schema": schema,
                        "path": str(file_path)
                    }
                    print(f"Registered tool: {schema['name']} ({tool_id})")
                    
        except Exception as e:
            print(f"Error loading module {file_path}: {e}")
            traceback.print_exc()

    def reload_file(self, file_path: str):
        path = Path(file_path)
        if not path.is_relative_to(self.tools_dir):
            return
            
        print(f"Reloading {file_path}...")
        # Remove old tools from this file
        self.tools = {k: v for k, v in self.tools.items() if v["path"] != str(path)}
        self.load_module(path)
        
    def get_tools_list(self):
        return [t["schema"] for t in self.tools.values()]
        
    def get_tool(self, tool_id):
        return self.tools.get(tool_id)
