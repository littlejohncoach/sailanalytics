import json
import importlib

# load registry once
with open("coach/metrics/registry.json") as f:
    REGISTRY = json.load(f)

def execute_metric(metric_id, df, params):

    # 1. validate
    if metric_id not in REGISTRY:
        return {
            "status": "error",
            "message": f"Metric '{metric_id}' not found"
        }

    # 2. resolve execution
    exec_info = REGISTRY[metric_id]["execution"]
    module_name = exec_info["module"]
    function_name = exec_info["function"]

    # 3. import function
    module = importlib.import_module(module_name)
    func = getattr(module, function_name)

    # 4. execute
    return func(df, params)
