#!/bin/sh
# Starts the guard with the first Python 3.8+ it finds. Without one, it still blocks anything that
# touches Basecamp or its credentials and lets every other tool call through, so a machine without
# Python is not locked out of Claude Code.
dir=$(dirname "$0")
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>/dev/null; then
    exec "$py" -I "$dir/guard.py"
  fi
done
input=$(cat)
case "$input" in
  *basecampapi.com*|*basecamp-manager/token*|*basecamp-manager/oauth.json*)
    printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Basecamp guard: Python 3.8 or later was not found, so Basecamp access is blocked. Install Python 3 and restart Claude Code."}}'
    ;;
esac
exit 0
