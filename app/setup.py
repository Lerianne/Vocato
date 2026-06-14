"""Vocato first-run setup — captures the user's name, pronouns, and weekly
check-in preference, then personalizes their sessions.

Run automatically on the first `vocato` launch, or any time via `vocato --setup`.

Privacy note: the name and pronouns are written to memory/identity.json, which
is git-ignored. They are injected into the coach's prompt at runtime — they are
never written into a tracked file, so your name never lands in the repo.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
MEMORY = ROOT / "memory"
IDENTITY_FILE = MEMORY / "identity.json"
TEMPLATE = ROOT / "examples" / "checkin.plist.template"
AGENT_DIR = Path.home() / "Library" / "LaunchAgents"
AGENT_PLIST = AGENT_DIR / "app.vocato.checkin.plist"

# Pronoun presets: subject / object / possessive adj / possessive pronoun / reflexive
PRONOUN_PRESETS = {
    "1": ("she", "her", "her", "hers", "herself"),
    "2": ("he", "him", "his", "his", "himself"),
    "3": ("they", "them", "their", "theirs", "themselves"),
}
WEEKDAYS = {  # launchd: Sunday = 0
    "sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
    "thursday": 4, "friday": 5, "saturday": 6,
}
WEEKDAY_NAMES = {v: k.capitalize() for k, v in WEEKDAYS.items()}


def _tty():
    """Read input from the real terminal even if stdin is piped."""
    try:
        return open("/dev/tty")
    except OSError:
        return sys.stdin


def ask(prompt: str, default: str = "", tty=None) -> str:
    suffix = f" [{default}]" if default else ""
    sys.stdout.write(f"{prompt}{suffix}: ")
    sys.stdout.flush()
    line = (tty or sys.stdin).readline()
    if not line:
        return default
    return line.strip() or default


def run_setup() -> dict:
    tty = _tty()
    print("\n🎯 Vocato setup — let's personalize your coach.\n")

    name = ask("Your name", tty=tty)

    print("\nPronouns:")
    print("  1) she/her   2) he/him   3) they/them   4) custom")
    choice = ask("Pick 1-4", "3", tty=tty)
    if choice in PRONOUN_PRESETS:
        subj, obj, poss, poss_p, refl = PRONOUN_PRESETS[choice]
    else:
        print("  Enter custom pronouns:")
        subj = ask("    subject (e.g. ze)", "they", tty=tty)
        obj = ask("    object (e.g. zir)", "them", tty=tty)
        poss = ask("    possessive (e.g. zir)", "their", tty=tty)
        poss_p = ask("    possessive pronoun (e.g. zirs)", "theirs", tty=tty)
        refl = ask("    reflexive (e.g. zirself)", "themselves", tty=tty)

    identity = {
        "name": name,
        "pronouns": {
            "subject": subj, "object": obj, "possessive": poss,
            "possessive_pronoun": poss_p, "reflexive": refl,
        },
    }

    # --- weekly check-in reminder -------------------------------------------
    want = ask("\nEnable a weekly coaching check-in reminder? (y/n)", "y", tty=tty)
    if want.lower().startswith("y"):
        day = ask("  Which day?", "Friday", tty=tty).strip().lower()
        weekday = WEEKDAYS.get(day, 5)
        time_str = ask("  What time? (24h HH:MM)", "16:00", tty=tty)
        try:
            hour, minute = (int(x) for x in time_str.split(":"))
        except ValueError:
            hour, minute = 16, 0
        identity["reminder"] = {"weekday": weekday, "hour": hour, "minute": minute}
        _install_reminder(weekday, hour, minute)
        print(f"  ✓ Weekly check-in set for {WEEKDAY_NAMES.get(weekday, 'Friday')} "
              f"at {hour:02d}:{minute:02d}.")
    else:
        identity["reminder"] = None
        _remove_reminder()
        print("  ✓ No weekly reminder (re-run setup any time to enable it).")

    MEMORY.mkdir(exist_ok=True)
    IDENTITY_FILE.write_text(json.dumps(identity, indent=2))
    print(f"\n✓ Saved to {IDENTITY_FILE} (git-ignored — stays on your machine).\n")
    return identity


def _install_reminder(weekday: int, hour: int, minute: int) -> None:
    if not TEMPLATE.exists():
        return
    plist = (TEMPLATE.read_text()
             .replace("__VOCATO_APP_DIR__", str(ROOT))
             .replace("__WEEKDAY__", str(weekday))
             .replace("__HOUR__", str(hour))
             .replace("__MINUTE__", str(minute)))
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    AGENT_PLIST.write_text(plist)
    # reload so the new schedule takes effect immediately
    subprocess.run(["launchctl", "unload", str(AGENT_PLIST)],
                   capture_output=True)
    subprocess.run(["launchctl", "load", str(AGENT_PLIST)], capture_output=True)


def _remove_reminder() -> None:
    if AGENT_PLIST.exists():
        subprocess.run(["launchctl", "unload", str(AGENT_PLIST)],
                       capture_output=True)
        AGENT_PLIST.unlink()


if __name__ == "__main__":
    run_setup()
