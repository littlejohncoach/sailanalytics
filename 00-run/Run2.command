#!/bin/zsh

echo "=== SailAnalytics: Run + Publish ==="

# -------------------------
# 1. RUN PIPELINE
# -------------------------
cd "/Users/marklittlejohn/Desktop/SailAnalytics/Arun" || exit

echo "Running pipeline..."
"/usr/local/bin/python3" "/Users/marklittlejohn/Desktop/SailAnalytics/Arun/run2.py"

# -------------------------
# 2. PUBLISH TO SERVER (GIT = UPLOAD)
# -------------------------
cd "/Users/marklittlejohn/Desktop/SailAnalytics" || exit

echo "Checking for changes..."

git add .

if git diff --cached --quiet; then

  echo "No changes detected → nothing to upload"

  osascript -e 'display dialog "No changes to publish.\nServer remains unchanged." buttons {"OK"} default button "OK"'

else

  echo "Changes detected → uploading to server..."

  git commit -m "auto publish $(date '+%Y-%m-%d %H:%M:%S')"
  git push

  echo "Upload complete → server updating..."

  osascript -e 'display dialog "Upload successful.\nServer will update in ~30–60 seconds." buttons {"OK"} default button "OK"'

fi