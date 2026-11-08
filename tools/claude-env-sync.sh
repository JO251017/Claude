#!/usr/bin/env bash
# no2 -> no1 Claude Code environment sync (macOS/Linux, bash)
# Usage:  no2:  ./claude-env-sync.sh export      -> ~/claude-env-bundle.tgz
#         no1:  ./claude-env-sync.sh import ~/claude-env-bundle.tgz
# Copies: skills, commands, agents, CLAUDE.md, settings.json, user-level MCP servers.
# Never copies: login tokens, session history, project history, caches.
set -euo pipefail
C="$HOME/.claude"
mode="${1:-}"

case "$mode" in
export)
  W="$(mktemp -d)"; mkdir -p "$W/claude"
  for p in skills commands agents CLAUDE.md settings.json; do
    [ -e "$C/$p" ] && cp -R "$C/$p" "$W/claude/$p"
  done
  # MCP servers only (no tokens/history from ~/.claude.json)
  python3 - "$W/mcp-servers.json" <<'PY'
import json, os, sys
p = os.path.expanduser("~/.claude.json")
d = json.load(open(p)) if os.path.exists(p) else {}
json.dump(d.get("mcpServers", {}), open(sys.argv[1], "w"), indent=2)
PY
  tar -czf "$HOME/claude-env-bundle.tgz" -C "$W" .
  echo "Created ~/claude-env-bundle.tgz"
  echo "Review mcp-servers.json for API keys in env/headers before sending:"
  echo "  tar -xzOf ~/claude-env-bundle.tgz ./mcp-servers.json"
  ;;
import)
  B="${2:?bundle path required}"
  W="$(mktemp -d)"; tar -xzf "$B" -C "$W"
  mkdir -p "$C"
  # Back up, then merge; existing no1 files win (cp -n), nothing is deleted.
  [ -d "$C" ] && cp -R "$C" "$C.bak.$(date +%Y%m%d%H%M%S)"
  cp -Rn "$W/claude/." "$C/"
  python3 - "$W/mcp-servers.json" <<'PY'
import json, os, sys
p = os.path.expanduser("~/.claude.json")
d = json.load(open(p)) if os.path.exists(p) else {}
src = json.load(open(sys.argv[1]))
cur = d.setdefault("mcpServers", {})
added = [k for k in src if k not in cur]
for k in added: cur[k] = src[k]
json.dump(d, open(p, "w"), indent=2)
print("MCP servers added:", added or "none (all already present)")
PY
  echo "Done. Restart Claude Code on no1, then run: claude mcp list"
  ;;
*) echo "usage: $0 export | import <bundle.tgz>"; exit 1;;
esac
