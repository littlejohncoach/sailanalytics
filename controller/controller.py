import json
from pathlib import Path
from openai import OpenAI

CONFIG = json.loads(Path("config.json").read_text())
ALLOWED_ROOT = Path(CONFIG["allowed_root"]).resolve()

def safe_path(p):
    full = (ALLOWED_ROOT / p).resolve()
    if not str(full).startswith(str(ALLOWED_ROOT)):
        raise Exception("Access denied outside SailAnalytics sandbox")
    return full

def list_dir(p=""):
    d = safe_path(p)
    return [x.name for x in d.iterdir()]

def read_file(p):
    f = safe_path(p)
    return f.read_text()[:12000]

client = OpenAI()

def ask_ai(prompt):
    extra = ""

    # auto load totalraces
    if "totalraces" in prompt.lower() or "william" in prompt.lower():
        try:
            files = [f for f in list_dir("data/totalraces") if "william" in f.lower()][:5]
            for f in files:
                txt = read_file(f"data/totalraces/{f}")
                extra += f"\nFILE: {f}\n{txt[:3000]}\n"
        except Exception as e:
            extra = f"\nDATA LOAD ERROR: {e}"

    full_prompt = f"""
You are SailAnalytics AI.

User request:
{prompt}

Available race data:
{extra}

Compute numerically.
Return only numbers.
"""

    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": full_prompt}],
    )

    return r.choices[0].message.content

if __name__ == "__main__":
    print("\nSailAnalytics Controller Ready")
    print("Sandbox root:", ALLOWED_ROOT)

    while True:
        cmd = input("\ncontroller> ")

        if cmd == "exit":
            break

        elif cmd == "ls":
            print(list_dir())

        elif cmd.startswith("ls "):
            print(list_dir(cmd[3:]))

        elif cmd.startswith("read "):
            print(read_file(cmd[5:]))

        elif cmd.startswith("ai "):
            print(ask_ai(cmd[3:]))

        elif cmd == "help":
            print("""
commands:
ls
ls data
ls data/totalraces
read data/file.csv
ai calculate william tacking angle
exit
""")

        else:
            print("unknown command")
