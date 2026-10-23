import re

from torque.skills.base import CONFIRM, SAFE, Skill
from torque.system.system_commands import ActionResult

STEP = 10       # percent per "up"/"down"


def _percent(match) -> int:
    return max(0, min(100, int(match.group("n"))))


def build_pc_skills(backend, notify=None):
    """The PC-control skills, bound to a backend (a fake in tests)."""

    def ok(message):
        return ActionResult(True, message)

    # ---- volume --------------------------------------------------

    def volume_set(m):
        level = _percent(m)
        backend.set_volume(level)
        return ok(f"Volume {level} percent.")

    def volume_step(direction):
        def run(_):
            backend.volume_step(direction, STEP // 2)
            return ok("Louder." if direction == "up" else "Quieter.")
        return run

    def mute(_):
        backend.media("mute")
        return ok("Toggled mute.")

    # ---- media ---------------------------------------------------

    def media(key, message):
        def run(_):
            backend.media(key)
            return ok(message)
        return run

    # ---- windows / system ---------------------------------------

    def screenshot(_):
        path = backend.screenshot()
        return ok(f"Screenshot saved to {path.parent.name} as {path.name}.")

    def lock(_):
        backend.lock()
        return ok("Locking.")

    def show_desktop(_):
        backend.show_desktop()
        return ok("Showing the desktop.")

    def switch_window(_):
        backend.switch_window()
        return ok("Switching window.")

    # ---- brightness ---------------------------------------------

    def brightness_set(m):
        level = _percent(m)
        backend.set_brightness(level)
        return ok(f"Brightness {level} percent.")

    def brightness_step(sign):
        def run(_):
            level = max(0, min(100, backend.get_brightness() + sign * STEP * 2))
            backend.set_brightness(level)
            return ok(f"Brightness {level} percent.")
        return run

    # ---- power (hard to undo: confirm first) -------------------

    def power(name, message):
        def run(_):
            getattr(backend, name)()
            return ok(message)
        return run

    pc = r"(?:my |the )?(?:pc|computer|laptop|machine)"
    vol = r"(?:the )?(?:volume|sound)"

    rules = [
        # name, tier, regex, action, prompt
        ("volume_set", SAFE,
         rf"(?:(?:set|turn|put|make) )?{vol}(?: to| at)? (?P<n>\d{{1,3}})(?: ?%| percent)?$",
         volume_set, ""),
        ("volume_up", SAFE,
         rf"(?:(?:turn|put|make) )?(?:{vol} up|it up|(?:it )?louder)(?: a bit| a little)?$|(?:increase|raise) {vol}$",
         volume_step("up"), ""),
        ("volume_down", SAFE,
         rf"(?:(?:turn|put|make) )?(?:{vol} down|it down|(?:it )?(?:quieter|softer))(?: a bit| a little)?$|(?:decrease|lower|reduce) {vol}$",
         volume_step("down"), ""),
        ("mute", SAFE, rf"(?:un)?mute(?: {vol}| (?:it|the sound))?$", mute, ""),

        ("play_pause", SAFE,
         r"(?:pause|resume|play|stop)(?: the)?(?: (?:music|song|media|video|playback))$|pause$|resume$",
         media("play_pause", "Okay."), ""),
        ("next_track", SAFE,
         r"(?:next (?:song|track)|skip(?: this| the)?(?: song| track)?|play the next (?:song|track))$",
         media("next", "Skipping."), ""),
        ("previous_track", SAFE,
         r"(?:previous (?:song|track)|last (?:song|track)|go back(?: a| one)?(?: song| track)|play the previous (?:song|track))$",
         media("previous", "Going back."), ""),

        ("screenshot", SAFE,
         r"(?:take (?:a )?screenshot|screenshot|capture (?:the |my )?screen|screen ?shot)(?: please)?$",
         screenshot, ""),
        ("lock", SAFE, rf"lock (?:{pc}|(?:the |my )?screen|it)$", lock, ""),
        ("show_desktop", SAFE,
         r"(?:show (?:me )?(?:the )?desktop|minimi[sz]e (?:all|everything|all windows|all of them))$",
         show_desktop, ""),
        ("switch_window", SAFE,
         r"(?:switch (?:the )?(?:window|windows|app|apps)|next window|alt tab)$",
         switch_window, ""),

        ("brightness_set", SAFE,
         r"(?:(?:set|turn|put|make) )?(?:the |my )?(?:screen )?brightness(?: to| at)? (?P<n>\d{1,3})(?: ?%| percent)?$",
         brightness_set, ""),
        ("brightness_up", SAFE,
         r"(?:(?:increase|raise|turn up) (?:the |my )?(?:screen )?brightness|brightness up|brighter|make it brighter)$",
         brightness_step(+1), ""),
        ("brightness_down", SAFE,
         r"(?:(?:decrease|lower|dim|turn down|reduce) (?:the |my )?(?:screen )?brightness|brightness down|dimmer|make it dimmer|dim the screen)$",
         brightness_step(-1), ""),

        ("shutdown", CONFIRM, rf"(?:shut ?down|power off|turn off) {pc}$|shut ?down$",
         power("shutdown", "Shutting down."), "Shut down the computer? Say yes to confirm."),
        ("restart", CONFIRM, rf"(?:restart|reboot) {pc}$|restart$|reboot$",
         power("restart", "Restarting."), "Restart the computer? Say yes to confirm."),
        ("sleep", CONFIRM,
         rf"(?:put {pc} to sleep|sleep {pc}|make {pc} sleep|go to sleep mode)$",
         power("sleep", "Going to sleep."), "Put the computer to sleep? Say yes to confirm."),
    ]

    return [
        Skill(name, tier, re.compile(pattern), action, prompt)
        for name, tier, pattern, action, prompt in rules
    ]
