import json
import re
import urllib.request

import dateparser
import pytz

def freeElectric():
    resp = urllib.request.urlopen("https://octopus.energy/free-electricity/")
    body = resp.read().decode("utf-8")
    if m := re.search(r"⚡️\s*\b.+(\w+ \d+\w* \w+) (\d+)([ap]m)?-(\d+)([ap]m)\b\s*⚡️", body):
        if m.group(3):
            date_from = m.expand(r"\1 \2\3")
        else:
            date_from = m.expand(r"\1 \2\5")
        date_to = m.expand(r"\1 \4\5")
        date_from = dateparser.parse(date_from)
        assert date_from
        date_to = dateparser.parse(date_to)
        assert date_to
        return date_from, date_to


