#!/bin/zsh

echo "=== SailAnalytics: Software Update ==="

cd "/Users/marklittlejohn/Desktop/SailAnalytics" || exit

echo ""
echo "Checking for changes..."

git add .

# Check if anything actually changed
if git diff --cached --quiet; then
  echo "No changes to commit."
else
  echo "Committing changes..."
  git commit -m "Software update"
fi

echo ""
echo "Pushing to GitHub..."

git push

echo ""
echo "Update complete."

read -k1 "Press any key to close..."