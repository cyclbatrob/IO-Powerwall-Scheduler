import json
import re
import urllib.request
from zoneinfo import ZoneInfo

import dateparser
import pytz

LONDON = ZoneInfo("Europe/London")

# Returns the start and end of the free electricity session advertised on the Octopus website as timezone aware
# (Europe/London) datetimes, or (None, None) if no session can be found. Never raises - a failure here must not stop
# the main script from updating the Powerwall, otherwise a finished session is left in the schedule.
def freeElectric():
    try:
        resp = urllib.request.urlopen("https://octopus.energy/free-electricity/", timeout=30)
        body = resp.read().decode("utf-8")
        if m := re.search(r"⚡️\s*\b.+(\w+ \d+\w* \w+) (\d+)([ap]m)?-(\d+)([ap]m)\b\s*⚡️", body):
            if m.group(3):
                date_from = m.expand(r"\1 \2\3")
            else:
                date_from = m.expand(r"\1 \2\5")
            date_to = m.expand(r"\1 \4\5")
            date_from = dateparser.parse(date_from)
            date_to = dateparser.parse(date_to)
            if date_from and date_to:
                # Times on the Octopus site are UK local time
                if date_from.tzinfo is None:
                    date_from = date_from.replace(tzinfo=LONDON)
                if date_to.tzinfo is None:
                    date_to = date_to.replace(tzinfo=LONDON)
                return date_from, date_to
    except Exception as err:
        print(f'Unable to check free electricity sessions: {err}')
    return None, None
