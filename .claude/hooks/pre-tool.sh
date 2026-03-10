#!/bin/bash
# Block destructive commands before they run
COMMAND="$CLAUDE_TOOL_INPUT"
if echo "$COMMAND" | grep -qE 'rm -rf|DROP TABLE|DELETE FROM [a-z]+ WHERE 1|truncate'; then
  echo "Blocked: destructive command requires explicit user confirmation."
  exit 2  # exit 2 = block the tool call, send message back to Claude
fi
exit 0  # allow everything else
