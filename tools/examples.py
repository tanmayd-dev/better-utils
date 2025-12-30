from core.decorators import tool
import time

@tool
def analyze_data(data_path: str, fast_mode: bool = False) -> dict:
    """
    Analyzes a data file and returns statistics.
    
    Args:
        data_path: Path to the CSV or JSON file
        fast_mode: If True, skips deep analysis for speed
    """
    time.sleep(1)
    return {
        "status": "success",
        "rows_processed": 1500,
        "analysis": "deep" if not fast_mode else "shallow",
        "timestamp": time.time()
    }

@tool
def generate_report(title: str, content: str, tags: list[str]) -> str:
    """
    Generates a formatted report.
    """
    return f"Report: {title}\nTags: {', '.join(tags)}\n\n{content}"

@tool
def calculate_metrics(values: list[float]) -> dict:
    """
    Calculates basic metrics from a list of numbers.
    """
    if not values:
        return {"error": "No values provided"}
        
    return {
        "count": len(values),
        "sum": sum(values),
        "average": sum(values) / len(values),
        "min": min(values),
        "max": max(values)
    }
