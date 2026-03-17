#!/bin/zsh

echo "=== SailAnalytics: Run + Publish ==="

# -------------------------
# 1. RUN DASHBOARD
# -------------------------
cd "/Users/marklittlejohn/Desktop/SailAnalytics/coach" || exit

echo "Launching dashboard..."
"/usr/local/bin/python3" "/Users/marklittlejohn/Desktop/SailAnalytics/coach/run_dashboard.py" &

# Give it a moment to start
sleep 3

# -------------------------
# 2. CHECK + PUBLISH
# -------------------------
cd "/Users/marklittlejohn/Desktop/SailAnalytics" || exit

git add .

# Check if there are staged changes
if git diff --cached --quiet; then

  osascript -e 'display dialog "Everything is up to date.\nNo new data to publish." buttons {"OK"} default button "OK"'

else

  git commit -m "auto publish $(date '+%Y-%m-%d %H:%M:%S')"
  git push

  osascript -e 'display dialog "New data published successfully.\nRender will update in ~30–60 seconds." buttons {"OK"} default button "OK"'

fi