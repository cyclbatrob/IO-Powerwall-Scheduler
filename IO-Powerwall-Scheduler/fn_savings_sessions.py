import requests,json
import datetime
from datetime import datetime, timezone
# Returns the start, end and export price (£/kWh) of today's next savings session, or 0,0,0 if there isn't one.
# Never raises - a failure here must not stop the main script from updating the Powerwall.
def saving_sessions(octopusURL,authToken,accountNumber):
        global DEBUG
        returnData=""
        query = """query savingSessions($account: String!) {
  savingSessions {
    account(accountNumber: $account) {
      hasJoinedCampaign
      joinedEvents {
        eventId
      }
      signedUpMeterPoint {
        mpan
      }
    }
    events {
      id
      code
      startAt
      endAt
      rewardPerKwhInOctoPoints
    }
  }
}
        """
        variables = {'account': str(accountNumber)}
        headers = {"Authorization": authToken}
        try:
           r = requests.post(octopusURL,json={'query': query, 'variables': variables},headers=headers)
#          print(r.text)
           timeNow = datetime.now().astimezone()
           for event in json.loads(r.text)["data"]["savingSessions"]["events"]:
              eventStart=datetime.strptime(event["startAt"],"%Y-%m-%dT%H:%M:%S%z")
              eventEnd=datetime.strptime(event["endAt"],"%Y-%m-%dT%H:%M:%S%z")
#             If the event has not yet passed, and is today, then return the start and end along with the price per Kwh exported (Octopoints/800 = £/Kwh)
              if(eventEnd>timeNow and eventStart.astimezone().date()==timeNow.date()):
                return eventStart,eventEnd,event["rewardPerKwhInOctoPoints"]/800
        except Exception as err:
           print(f'Unable to check savings sessions: {err}')
#       No savings sessions, so return all zeros
        return 0,0,0
