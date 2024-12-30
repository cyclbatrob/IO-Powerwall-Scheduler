import requests,json
import datetime
from datetime import datetime, timezone
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
        r = requests.post(octopusURL,json={'query': query, 'variables': variables},headers=headers)
#        print(r.text)
        for event in json.loads(r.text)["data"]["savingSessions"]["events"]:
           eventStart=datetime.strptime(event["startAt"],"%Y-%m-%dT%H:%M:%S%z")
           eventEnd=datetime.strptime(event["endAt"],"%Y-%m-%dT%H:%M:%S%z")
#          If the event has not yet passed, and is today, then return the start and end along with the price per Kwh exported (Octopoints/800 = £/Kwh)
           if(eventEnd>datetime.now().astimezone() and eventStart.day==datetime.now().astimezone.day):
             return eventStart,eventEnd,rewardPerKwhInOctoPoints/800
           else:
#            No savings sessions, so return all zeros
             return 0,0,0
