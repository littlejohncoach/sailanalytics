import os
import json
import io
import glob
import contextlib
import threading

import pandas as pd
from openai import OpenAI

# UI
import tkinter as tk
from tkinter import scrolledtext
import speech_recognition as sr

# -----------------------------
# PATHS
# -----------------------------
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(AGENT_DIR, ".."))
MEMORY_DIR = os.path.join(AGENT_DIR, "memory")

KNOWLEDGE_FILE = os.path.join(MEMORY_DIR, "knowledge.json")

os.chdir(ROOT)

# -----------------------------
# ENV
# -----------------------------
env_path = os.path.join(AGENT_DIR, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ[k] = v

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# -----------------------------
# MEMORY
# -----------------------------
def load_memory():

    memory = {}

    if not os.path.exists(MEMORY_DIR):
        return {}

    for file in sorted(os.listdir(MEMORY_DIR)):
        if not file.endswith(".json"):
            continue

        path = os.path.join(MEMORY_DIR, file)

        try:
            with open(path) as f:
                data = json.load(f)

                # merge top-level
                if isinstance(data, dict):
                    memory[file.replace(".json", "")] = data

        except Exception:
            continue

    return memory
    try:
        with open(KNOWLEDGE_FILE) as f:
            return json.load(f)
    except:
        return {}

# -----------------------------
# SAFE PATH
# -----------------------------
def safe_path(path):
    full = os.path.abspath(os.path.join(ROOT, path))
    if not full.startswith(ROOT):
        raise ValueError("Path outside root not allowed")
    return full

# -----------------------------
# TOOLS
# -----------------------------
def tool_list_dir(path="."):
    full = safe_path(path)
    return json.dumps({
        "path": path,
        "items": sorted(os.listdir(full))
    }, indent=2)

def tool_read_file(path):
    full = safe_path(path)

    if os.path.isdir(full):
        return tool_list_dir(path)

    if full.lower().endswith(".csv"):
        df = pd.read_csv(full, nrows=5, engine="python", on_bad_lines="skip")
        return json.dumps({
            "columns": list(df.columns),
            "preview": df.head(5).to_dict(orient="records")
        }, indent=2)

    with open(full, "r", errors="ignore") as f:
        return f.read()

def tool_read_memory():
    return json.dumps(load_memory(), indent=2)

# -----------------------------
# READ ONLY PYTHON
# -----------------------------
def tool_run_python(code):

    forbidden = [
        "open(",
        "write(",
        "remove(",
        "unlink(",
        "rmtree(",
        "mkdir(",
        "rename(",
        "shutil",
        "subprocess",
        "os.system",
        ".to_csv(",
        ".to_json(",
        ".to_parquet("
    ]

    for f in forbidden:
        if f in code:
            raise ValueError("WRITE BLOCKED (READ ONLY MODE)")

    local = {}
    stdout = io.StringIO()

    globals_safe = {
        "__builtins__": __builtins__,
        "pd": pd,
        "os": os,
        "json": json,
        "glob": glob,
        "ROOT": ROOT
    }

    with contextlib.redirect_stdout(stdout):
        exec(code, globals_safe, local)

    return json.dumps({
        "stdout": stdout.getvalue(),
        "result": local.get("result", None)
    }, indent=2, default=str)

# -----------------------------
# METRIC EXECUTION (PATCH)
# -----------------------------
import sys
sys.path.append(ROOT)

from coach.metrics.executor import execute_metric

def tool_execute_metric(metric_id, file_path, leg_id=None):
    full = safe_path(file_path)
    df = pd.read_csv(full, engine="python", on_bad_lines="skip")

    params = {}
    if leg_id is not None:
        params["leg_id"] = leg_id

    return json.dumps(
        execute_metric(metric_id, df, params),
        indent=2,
        default=str
    )

# -----------------------------
# TOOLS DEF
# -----------------------------
TOOLS = [
    {
        "type": "function",
        "name": "execute_metric",
        "parameters": {
            "type": "object",
            "properties": {
                "metric_id": {"type": "string"},
                "file_path": {"type": "string"},
                "leg_id": {"type": "integer"}
            },
            "required": ["metric_id", "file_path"]
        }
    },

    {
        "type": "function",
        "name": "list_dir",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    },
    {
        "type": "function",
        "name": "read_file",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    },
    {
        "type": "function",
        "name": "read_memory",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "type": "function",
        "name": "run_python",
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"]
        }
    }
]

# -----------------------------
# TOOL ROUTER
# -----------------------------
def call_tool(name, args):

    if name == "list_dir":
        return tool_list_dir(**args)

    if name == "read_file":
        return tool_read_file(**args)

    if name == "read_memory":
        return tool_read_memory()

    if name == "run_python":
        return tool_run_python(**args)

    if name == "execute_metric":
        return tool_execute_metric(**args)

    raise ValueError("Unknown tool")

# -----------------------------
# SYSTEM
# -----------------------------
SYSTEM = """
You are VREA.

CRITICAL RULES:
- All metrics MUST be executed via the execute_metric tool
- You are NOT allowed to compute metrics manually
- You are NOT allowed to infer metrics from CSV columns
- If a metric exists in the registry, you MUST call execute_metric
- If you cannot call execute_metric, return execution_not_available

DO NOT:
- inspect CSV columns to answer metric questions
- approximate or derive metrics yourself

You may only:
- locate correct file_path
- call execute_metric with correct parameters

Available metric_ids:
- tack_count
- tack_angle
"""

# -----------------------------
# ASK
# -----------------------------
def ask(q):

    r = client.responses.create(
        model="gpt-5.4",
        instructions=SYSTEM,
        input=q,
        tools=TOOLS,
        tool_choice="auto"
    )

    while True:

        calls = [x for x in r.output if x.type == "function_call"]

        if not calls:
            return r.output_text

        outputs = []

        for call in calls:
            args = json.loads(call.arguments) if call.arguments else {}
            out = call_tool(call.name, args)

            outputs.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": out
            })

        r = client.responses.create(
            model="gpt-5.4",
            previous_response_id=r.id,
            input=outputs,
            tools=TOOLS,
            tool_choice="auto"
        )

# -----------------------------
# SPEECH
# -----------------------------
def speak():
    output_box.delete("1.0", tk.END)
    output_box.insert(tk.END, "Listening...\n")

    r = sr.Recognizer()

    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.3)
        audio = r.listen(source)

    try:
        text = r.recognize_google(audio)
        input_box.delete("1.0", tk.END)
        input_box.insert(tk.END, text)
        run_query()

    except Exception as e:
        output_box.delete("1.0", tk.END)
        output_box.insert(tk.END, f"Speech error: {e}")

# -----------------------------
# RUN QUERY
# -----------------------------
def run_query():
    q = input_box.get("1.0", tk.END).strip()
    if not q:
        return

    output_box.delete("1.0", tk.END)
    output_box.insert(tk.END, "Thinking...\n")
    root.update()

    def worker():
        try:
            result = ask(q)
        except Exception as e:
            result = f"Error: {e}"

        output_box.delete("1.0", tk.END)
        output_box.insert(tk.END, result)

    threading.Thread(target=worker).start()

# -----------------------------
# UI
# -----------------------------
root = tk.Tk()
root.title("SailAnalytics Agent")
root.geometry("720x520")
root.configure(bg="#f5f5f5")

tk.Label(root, text="Question", bg="#f5f5f5",
         font=("Helvetica", 12, "bold")).pack(anchor="w", padx=10)

input_box = scrolledtext.ScrolledText(
    root,
    height=4,
    font=("Helvetica", 13),
    wrap=tk.WORD
)
input_box.pack(fill="both", padx=10, pady=5)

btn_frame = tk.Frame(root, bg="#f5f5f5")
btn_frame.pack(pady=5)

tk.Button(
    btn_frame,
    text="🎤 Speak",
    command=lambda: threading.Thread(target=speak).start(),
    width=10
).pack(side="left", padx=5)

tk.Button(
    btn_frame,
    text="Ask",
    command=run_query,
    width=10
).pack(side="left", padx=5)

tk.Label(root, text="Answer", bg="#f5f5f5",
         font=("Helvetica", 12, "bold")).pack(anchor="w", padx=10)

output_box = scrolledtext.ScrolledText(
    root,
    height=18,
    font=("Helvetica", 13),
    wrap=tk.WORD
)
output_box.pack(fill="both", expand=True, padx=10, pady=5)

root.mainloop()
