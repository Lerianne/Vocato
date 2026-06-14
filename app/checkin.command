#!/bin/zsh
# Vocato weekly check-in — double-clickable, and opened by the launchd reminder.
# Opening a .command file launches Terminal and runs it, with no AppleScript /
# Automation permission required (unlike `tell application "Terminal"`).
cd "$(dirname "$0")"
exec ./coach --checkin
