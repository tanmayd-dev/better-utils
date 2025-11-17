from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time

class ToolHandler(FileSystemEventHandler):
    def __init__(self, registry):
        self.registry = registry
        
    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            self.registry.reload_file(event.src_path)

    def on_created(self, event):
        if event.src_path.endswith(".py"):
            self.registry.reload_file(event.src_path)

def start_watcher(registry, path):
    event_handler = ToolHandler(registry)
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    return observer
