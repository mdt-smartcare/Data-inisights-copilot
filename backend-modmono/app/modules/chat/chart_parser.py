"""
Chart data parser for extracting visualization data from LLM responses.

Parses JSON blocks from LLM outputs to generate chart configurations
compatible with the frontend ChartRenderer component.
"""
import re
import json
from typing import Optional, Tuple, List, Dict, Any

from app.core.utils.logging import get_logger
from app.modules.chat.schemas import ChartData

logger = get_logger(__name__)


def _sanitize_json_string(json_str: str) -> str:
    """
    Sanitize a JSON string to fix common LLM formatting errors.
    
    Fixes:
    - Trailing commas before closing brackets/braces
    - Missing commas between elements
    - Single quotes instead of double quotes
    
    Args:
        json_str: The raw JSON string from LLM
        
    Returns:
        Sanitized JSON string
    """
    # Remove any leading/trailing whitespace
    sanitized = json_str.strip()
    
    # Fix trailing commas before closing brackets/braces
    # e.g., [1, 2, 3,] -> [1, 2, 3]
    sanitized = re.sub(r',\s*([}\]])', r'\1', sanitized)
    
    # Fix missing commas between array elements (number followed by number/string/object)
    sanitized = re.sub(r'(\d)\s+(\d)', r'\1, \2', sanitized)
    sanitized = re.sub(r'"\s+(?=")', '", ', sanitized)
    sanitized = re.sub(r'(\d)\s+(?=")', r'\1, ', sanitized)
    sanitized = re.sub(r'"\s+(\d)', r'", \1', sanitized)
    
    # Fix missing commas between object properties
    sanitized = re.sub(r'(\"[^"]*\")\s*:\s*([^,}\]]+)\s+(?=\")', r'\1: \2, ', sanitized)
    
    # Fix missing comma after closing brace/bracket followed by opening quote
    sanitized = re.sub(r'([}\]])\s+(?=")', r'\1, ', sanitized)
    
    # Replace single quotes with double quotes (simple cases only)
    if "'" in sanitized and '"' not in sanitized:
        sanitized = sanitized.replace("'", '"')
    
    return sanitized


def _try_parse_json(json_str: str) -> Optional[Dict[str, Any]]:
    """
    Try to parse JSON with multiple fallback strategies.
    
    Args:
        json_str: The JSON string to parse
        
    Returns:
        Parsed dict or None if all strategies fail
    """
    # Strategy 1: Direct parse
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Sanitize and retry
    try:
        sanitized = _sanitize_json_string(json_str)
        return json.loads(sanitized)
    except json.JSONDecodeError:
        pass
    
    # Strategy 3: Try to extract just the object/array part
    try:
        start_obj = json_str.find('{')
        start_arr = json_str.find('[')
        
        if start_obj == -1 and start_arr == -1:
            return None
            
        if start_obj == -1:
            start = start_arr
            end_char = ']'
        elif start_arr == -1:
            start = start_obj
            end_char = '}'
        else:
            start = min(start_obj, start_arr)
            end_char = '}' if start == start_obj else ']'
        
        end = json_str.rfind(end_char)
        if end > start:
            extracted = json_str[start:end + 1]
            sanitized = _sanitize_json_string(extracted)
            return json.loads(sanitized)
    except json.JSONDecodeError:
        pass
    
    # Strategy 4: Try with ast.literal_eval as last resort
    try:
        import ast
        py_str = json_str.replace('null', 'None').replace('true', 'True').replace('false', 'False')
        result = ast.literal_eval(py_str)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError):
        pass
    
    return None


def parse_chart_data(response: str) -> Tuple[Optional[ChartData], str]:
    """
    Parse chart data from an LLM response.
    
    Extracts JSON blocks containing chart configurations and returns
    a ChartData object along with the cleaned response text.
    
    Args:
        response: The full LLM response text
        
    Returns:
        Tuple of (ChartData or None, cleaned response text)
    """
    chart_data = None
    cleaned_response = response
    
    # Try to extract JSON block - handle nested braces properly
    # Look for ```json ... ``` block
    json_match = re.search(r'''```json\s*([\s\S]*?)\s*```''', response)
    
    if json_match:
        json_str = json_match.group(1).strip()
        
        # Use robust JSON parsing with sanitization
        data = _try_parse_json(json_str)
        
        if data:
            try:
                # Extract chart data - handle both wrapped and direct formats
                chart_json = None
                if "chart_json" in data:
                    chart_json = data["chart_json"]
                elif "type" in data and ("data" in data or "value" in data):
                    # LLM returned the chart object directly
                    chart_json = data
                
                if chart_json:
                    chart_data = _validate_and_create_chart(chart_json)
                    
                    if chart_data:
                        logger.info(f"Successfully parsed chart data: {chart_data.title or 'Untitled'}")
            except Exception as e:
                logger.warning(f"Failed to create ChartData: {e}")
        else:
            logger.warning(f"Failed to parse chart JSON after all retry strategies")
            logger.debug(f"JSON string was: {json_str[:500]}...")
    
    # Clean the response by removing JSON blocks
    cleaned_response = clean_response_text(response)
    
    return chart_data, cleaned_response


def _validate_and_create_chart(chart_json: Dict[str, Any]) -> Optional[ChartData]:
    """
    Validate chart JSON and create a ChartData object.
    
    Handles compatibility fixes and auto-generation of missing fields.
    """
    try:
        # Compatibility fix for Chart.js style output (datasets) -> Frontend style (values)
        if "data" in chart_json and isinstance(chart_json["data"], dict):
            cdata = chart_json["data"]
            if "datasets" in cdata and "values" not in cdata:
                # Extract data from first dataset
                try:
                    datasets = cdata["datasets"]
                    if datasets and isinstance(datasets, list):
                        cdata["values"] = datasets[0].get("data", [])
                        logger.info("Transformed Chart.js style 'datasets' to 'values'")
                except Exception as e:
                    logger.warning(f"Failed to transform chart datasets: {e}")
        
        # Auto-generate title if missing
        if "title" not in chart_json or not chart_json["title"]:
            chart_type = chart_json.get("type", "Chart")
            chart_json["title"] = f"{chart_type.capitalize()} Visualization"
            logger.info(f"Auto-generated missing chart title: {chart_json['title']}")
        
        # Validate required fields
        if "type" not in chart_json:
            logger.warning("Chart JSON missing required 'type' field")
            return None
        
        # Create ChartData object
        return ChartData(**chart_json)
        
    except Exception as e:
        logger.warning(f"Validation failed for chart data: {e}")
        return None


def clean_response_text(response: str) -> str:
    """
    Remove JSON code blocks from response text.
    
    Args:
        response: The full response text
        
    Returns:
        Cleaned text with JSON blocks removed
    """
    # Remove JSON code blocks - use [\s\S]*? to match across newlines
    cleaned = re.sub(r'''```json\s*[\s\S]*?\s*```''', '', response)
    return cleaned.strip()
