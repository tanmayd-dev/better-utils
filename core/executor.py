import inspect
from fastapi import UploadFile
from PIL import Image
import io

from typing import Annotated, get_origin, get_args

async def execute_tool(tool_def, args: dict):
    func = tool_def["func"]
    sig = inspect.signature(func)
    call_args = {}
    
    for param_name, param in sig.parameters.items():
        if param_name in args:
            val = args[param_name]
            
            annotation = param.annotation
            if get_origin(annotation) == Annotated:
                annotation = get_args(annotation)[0]
            
            
            is_image = False
            try:
                if annotation == Image.Image:
                    is_image = True
                elif hasattr(annotation, "__name__") and annotation.__name__ == "Image":
                    is_image = True
                elif str(annotation) == "<class 'PIL.Image.Image'>":
                    is_image = True
            except:
                pass
            
            is_upload_file = isinstance(val, UploadFile) or type(val).__name__ == 'UploadFile'
            
            if is_image and is_upload_file:
                content = await val.read()
                val = Image.open(io.BytesIO(content))
            elif annotation == int:
                val = int(val)
            elif annotation == float:
                val = float(val)
            elif annotation == bool:
                 # Handle string "true"/"false" from form data if needed, 
                 # though FastAPI/Pydantic usually handles this if we use a model.
                 # But here we are parsing raw dict or form data manually-ish.
                 if isinstance(val, str):
                     val = val.lower() == "true"
            
            call_args[param_name] = val
            
    result = func(**call_args)
    
    # Handle result conversion
    if isinstance(result, Image.Image):
        # Return as bytes for the API to stream
        img_byte_arr = io.BytesIO()
        result.save(img_byte_arr, format='PNG')
        return {"type": "image", "data": img_byte_arr.getvalue(), "mime": "image/png"}
        
    return {"type": "text", "data": str(result)}
