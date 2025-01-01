#-----------------------------------------------------------------------------------------------------------------------------#
#--                                                                                                                         --#
#--                                          Intelligent Octopus Powerwall Scheduler                                        --#
#--                                                                                                                         --#
#--  Tool to align the Tesla Powerwall schedule with the off-peak slots provided by Intelligent Octopus. The base slot of   --#
#--  23:30 -> 05:30 is easy to manage, but when Octopus provides off-peak car charging slots outside of this, the result    --#
#--  can be the Powerwall dumping into the car. This may result in the Powerwall not having enough to run the house until   --#
#--  the next off-peak slot.                                                                                                --#
#--  This tool, pulls the slots from Octopus and drops them into the tariff schedule for Octopus. Currently the rates are   --#
#--  configurable within this script, but static.                                                                           --#
#--                                                                                                                         --#
#--  Savings sessions are also handled, although very much in testing at the moment. The tool will pull savings sessions    --#
#--  from Octopus, filter out previous sessions, and add the start, end and export rate into the powerwall. This enables    --#
#--  the Powerwall to behave accordingly.                                                                                   --#
#--                                                                                                                         --#
#--  Author: Robin Taylor                                                                                                   --#
#--                                                                                                                         --#
#-----------------------------------------------------------------------------------------------------------------------------#

#---------------------------------------#
#--                                   --#
#--         Version History           --#
#--                                   --#
#---------------------------------------#

#  22/11/2024 --- v0.5 - Initial version - includes basic off-peak slots with static rates. Savings sessions in draft 
#  10/12/2024 --- v0.6 - Added MQTT integration to remotely enable/disable the automation

#-----------------------------------------------------------------------------------------------------------------------------#
#-----------------------------------------------------------------------------------------------------------------------------#

#!/usr/bin/env python
import requests,json
import math
import hashlib
import datetime
import pytz
import time
import sys
from datetime import date, datetime,timezone,timedelta
from requests.models import HTTPError
from zoneinfo import ZoneInfo
from paho.mqtt import client as mqtt_client

#import Precondition
import fn_savings_sessions
import check_free_electricity

# Key script variables for debugging only
READONLY = False # Prevents updating the Powerwall schedule - just shows what the script would do
FORCEUPDATE = False # To be used if needing to force an update to the Powerwall.
DEBUG = False
LOG_FILE = "IO-Update-Powerwall-Schedule.log"
CONFIG_FILE = "config.txt"
ENABLE_PRECONDITION = False

# Defaut tariff rates - buy and sell (£) - we default savings to £0.00 because it's variable, but we need something in there
# Onpeak & offpeak rates are overridden by config file. Free rates are always 0, savings rates are dynamically updated dependent on offer
OFFPEAK_RATE = 0.07
ONPEAK_RATE = 0.25
FREE_RATE = 0.00
SAVINGS_RATE = 0.00
OFFPEAK_SELL_RATE = 0.00
ONPEAK_SELL_RATE = 0.15
FREE_SELL_RATE = 0.00
SAVINGS_SELL_RATE = 0.00
# Minimum amount above standard rate required to participate in savings session in GBP
SAVINGS_MIN_OFFSET = 0.00

# To avoid participating in free electricity or savings sessions, set to False
PARTICIPATE_FREE_ELECTRIC = True
PARTICIPATE_SAVING_SESSIONS = False

if(len(sys.argv)==3):
  CONFIG_FILE=sys.argv[1]
  LOG_FILE=sys.argv[2]
elif(len(sys.argv)==2):
  CONFIG_FILE=sys.argv[1]
elif(DEBUG):
  print(f"No config/log file set - using defaults - Config File: {CONFIG_FILE} - Log File: {LOG_FILE}\n")
if(DEBUG):
  print(f"Using Config File: {CONFIG_FILE} - Log File: {LOG_FILE}\n")

try:
   f = open(LOG_FILE,"r")
except:
   print("Log file does not exist. Creating...\n")
   f = open(LOG_FILE,"w")
   f.close()

try:
   f = open(CONFIG_FILE,"r")
except:
   print("Config file does not exist. Creating...\n")
   print("Please edit the config file ("+CONFIG_FILE+") before next use\n")
   f = open(CONFIG_FILE,"w")
   f.write("""
# Set to True to participate, False to avoid - Default = True
FREE_ELECTRIC True
SAVINGS_SESSIONS False

# Tariff Rates
OFFPEAK_RATE 0.07
OFFPEAK_SELL_RATE 0.06
ONPEAK_RATE 0.25
ONPEAK_SELL_RATE 0.15

# Minimum amount (£) over standard export rate before exporting during savings session - default 0
SAVINGS_MIN_OFFSET 0.00

TESSIE_API_KEY XXXXXXXXXXXXXXXXXXXXXXXXXXX
# Powerwall site ID - can be found by running getsiteID.py
TESLA_SITE_ID XXXXXXXXXXXXXXXX

# Octopus details
OCTOPUS_API_KEY sk_live_XXXXXXXXXXXXXXXXXXXXXXXX
OCTOPUS_ACCOUNT_NUMBER A-99999999

# Debugging Options. Uncomment as required. FORCE_UPDATE will update the Powerwall schedule regardless of any change, but READONLY takes precedence     
DEBUG True
#READONLY True
#FORCE_UPDATE True 


#-------------------------------------------------#
#    Powerwall-Limit-Export specific options      #
#-------------------------------------------------#

# Number of hours before off-peak when export is to be re-enabled. Default of 4 hours means if off-peak is 23:30, export will be re-enabled at 19:30.
# Configure this to suit your Powerwall size + export rate. If SAVINGS_SESSIONS is set to True, 16:00-19:00 is always excluded from export to maximise savings.
REENABLE_EXPORT_OFFSET 4

# Debugging options for Powerwall-Limit-Export
#DEBUG_PW_LIMIT True
#READONLY_PW_LIMIT True

#-------------------------------#
#    MQTT specific options      #
#-------------------------------#
MQTT_ENABLE False
MQTT_BROKER XXXXXXXX
MQTT_PORT 1883
MQTT_USER XXXXXXXXX
MQTT_PWD XXXXXXXXXXXXXX
MQTT_TOPIC XXXXXXXXXXXXXXXXXXXXXXXXXX
""")
   quit()

for line in f:
  if(line!="\n" and line.strip()!="" and line.strip()[0]!="#"):
    linesplit = line.strip().split(" ")
    if(linesplit[0] == "OFFPEAK_RATE"):
      OFFPEAK_RATE = linesplit[1]
    elif(linesplit[0] == "OFFPEAK_SELL_RATE"):
      OFFPEAK_SELL_RATE = linesplit[1]
    elif(linesplit[0] == "ONPEAK_RATE"):
      ONPEAK_RATE = linesplit[1]
    elif(linesplit[0] == "ONPEAK_SELL_RATE"):
      ONPEAK_SELL_RATE = linesplit[1]
    elif(linesplit[0] == "SAVINGS_MIN_OFFSET"):
      SAVINGS_MIN_OFFSET = linesplit[1]
    elif(linesplit[0] == "TESSIE_API_KEY"):
      tessieapikey = linesplit[1]
    elif(linesplit[0] == "TESLA_SITE_ID"):
      teslasiteid = linesplit[1]
    elif(linesplit[0] == "OCTOPUS_API_KEY"):
      apikey = linesplit[1]
    elif(linesplit[0] == "OCTOPUS_ACCOUNT_NUMBER"):
      accountNumber = linesplit[1]
    elif(linesplit[0] == "FREE_ELECTRIC"):
      PARTICIPATE_FREE_ELECTRIC = linesplit[1]
    elif(linesplit[0] == "SAVINGS_SESSIONS"):
      PARTICIPATE_SAVING_SESSIONS = linesplit[1]
    elif(linesplit[0] == "DEBUG"):
      DEBUG = linesplit[1]
    elif(linesplit[0] == "READONLY"):
      READONLY = linesplit[1]
    elif(linesplit[0] == "FORCE_UPDATE"):
      FORCE_UPDATE = linesplit[1]
    elif(linesplit[0] == "MQTT_ENABLE"):
      MQTT_Enable = linesplit[1]
    elif(linesplit[0] == "MQTT_BROKER"):
      MQTT_Broker = linesplit[1]
    elif(linesplit[0] == "MQTT_PORT"):
      MQTT_Port = linesplit[1]
    elif(linesplit[0] == "MQTT_USER"):
      MQTT_User = linesplit[1]
    elif(linesplit[0] == "MQTT_PWD"):
      MQTT_Pwd = linesplit[1]
    elif(linesplit[0] == "MQTT_TOPIC"):
      MQTT_Topic = linesplit[1]
f.close()


# Key URLs
# DO NOT CHANGE! Will break the script
octopusURL = "https://api.octopus.energy/v1/graphql/" # Do not change
teslaurl = "https://api.tessie.com/api/1/energy_sites/"+teslasiteid+"/time_of_use_settings" # API URL for updating Powerwall Schedule

# variables to be used for the slots - just because comparing integers is safer than strings 
# DO NOT CHANGE! Will break the script
SLOT_OFFPEAK=1
SLOT_ONPEAK=2
SLOT_SAVINGS=3
SLOT_FREE=4


#--------------------------------------------------------------------------------------------------------------------
# This section uses an MQTT trigger to determine whether the automation should run or not.
# Using the MQTT_TOPIC as defined in the config it will run the script or quit. "off" will stop
# the script from running. Any other response will result in the script running.
#--------------------------------------------------------------------------------------------------------------------
def connect_mqtt():
    #def on_connect(client, userdata, flags, rc):
    # For paho-mqtt 2.0.0, you need to add the properties parameter.
    def on_connect(client, userdata, flags, rc, properties):
        if(rc == 0 and DEBUG):
            print("Connected to MQTT Broker!")
        elif(DEBUG):
            print("Failed to connect, return code %d\n", rc)
    # Set Connecting Client ID
    #client = mqtt_client.Client(MQTT_ClientID)

    # For paho-mqtt 2.0.0, you need to set callback_api_version.
    client = mqtt_client.Client(client_id=MQTT_ClientID, callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2)

    client.username_pw_set(MQTT_User, MQTT_Pwd)
    client.on_connect = on_connect
    client.connect(MQTT_Broker, int(MQTT_Port))
    return client

def subscribe(client: mqtt_client):
    def on_message(client, userdata, msg):
       if(DEBUG):
          print(f"MQTT message received: {msg.payload.decode()}")
       if(str(msg.payload.decode())=="off"):
          print("MQTT message received: Automation Disabled - Quitting")
          quit()
       elif(DEBUG):
          print("MQTT message received: Automation Enabled - Continuing")
       client.disconnect()
    client.subscribe(MQTT_Topic)
    client.on_message = on_message

if(MQTT_Enable == True):
  MQTT_ClientID = "Client-"+MQTT_User
  client = connect_mqtt()
  subscribe(client)
  client.loop_forever()

#--------------------------------------------------------------------------------------------------------------------

if READONLY:
   print("---------------------------------------------------")
   print("-- READONLY Mode - Will NOT update the Tesla API --")
   print("---------------------------------------------------")

if FORCEUPDATE:
   print("-----------------------------------------")
   print("-- FORCEUPDATE Mode - Will ignore hash --")
   print("-- READONLY mode takes precedent       --")
   print("-----------------------------------------")



def LogMsg(severity,message):
   if not READONLY:
     f = open(LOG_FILE,"a")
     current_time = datetime.now()
     f.write(str(current_time) + " - " + severity + " - " + message + "\n")
     f.close()
   if(DEBUG):
     print("Log: "+severity + ' - ' + message)


# This file holds the hash of the last known "outputJSON" which is the off-peak slots.
# It just lets us know whether the slots have changed from each execution so we're not persistently updating the Tesla API with no changes
try:
   f = open("IO-Changed-Hash","r")
   changedHash = f.read().strip("\n")
   if DEBUG:
      print("Hash read from file: "+changedHash)
   f.close()
except:
   changedHash = ""
   print("Hash file does not exist. Will create.")

# Create the base start & end text for each period. Could probably do this more efficiently but maybe in a future version
OctopusOffPeakTimeSlotBaseStart = """
               "OFF_PEAK": {
                  "periods": [
"""
OctopusOffPeakTimeSlotBaseEnd = """                   ]
                },
"""
OctopusOnPeakTimeSlotBaseStart = """
               "ON_PEAK": {
                  "periods": [
"""
OctopusOnPeakTimeSlotBaseEnd = """                   ]
                }
"""
OctopusFreeTimeSlotBaseStart = """
               "SUPER_OFF_PEAK": {
                  "periods": [
"""
OctopusFreeTimeSlotBaseEnd = """                   ]
                }
"""
OctopusSavingsTimeSlotBaseStart = """
               "MID_PEAK": {
                  "periods": [
"""
OctopusSavingsTimeSlotBaseEnd = """                   ]
                }
"""


dateTimeToUse = datetime.now().astimezone()
#if dateTimeToUse.hour < 17:
#    dateTimeToUse = dateTimeToUse-timedelta(days=1)
ioStart = dateTimeToUse.astimezone().replace(hour=23, minute=30, second=0, microsecond=0)
ioEnd = dateTimeToUse.astimezone().replace(microsecond=0).replace(hour=5, minute=30, second=0, microsecond=0)+timedelta(days = 1)
#print(str(ioStart)+str(ioEnd))
def refreshToken(apiKey,accountNumber):
    try:
        query = """
        mutation krakenTokenAuthentication($api: String!) {
        obtainKrakenToken(input: {APIKey: $api}) {
            token
        }
        }
        """
        variables = {'api': apikey}
        r = requests.post(octopusURL, json={'query': query , 'variables': variables})
    except HTTPError as http_err:
        print(f'HTTP Error {http_err}')
    except Exception as err:
        print(f'Another error occurred: {err}')

    jsonResponse = json.loads(r.text)
    return jsonResponse['data']['obtainKrakenToken']['token']

def getObject():
    try:
        query = """
            query getData($input: String!) {
                plannedDispatches(accountNumber: $input) {
                    startDt
                    endDt
                }
            }
        """
        if DEBUG:
          print('Get Octopus Dispatches Query: ' + query)
        variables = {'input': accountNumber}
        headers={"Authorization": authToken}
        r = requests.post(octopusURL, json={'query': query , 'variables': variables, 'operationName': 'getData'},headers=headers)
        if DEBUG:
           print("Octopus Dispatches Returned Data:\n"+str(json.loads(r.text)['data']))
        return json.loads(r.text)['data']
    except HTTPError as http_err:
        print(f'HTTP Error {http_err}')
    except Exception as err:
        print(f'Another error occurred: {err}')

def fillSlots(SLOT_RATE, startTime, endTime):
   # convert start time to minutes since 00:00
   startMinutes = int(startTime.hour)*60+int(startTime.minute)
   endMinutes = int(endTime.hour)*60+int(endTime.minute)

   # if start time is greater than end time then we must be crossing the midnight boundary, so need to cater for that
   if(startMinutes>endMinutes):
     for i in range(math.floor(startMinutes/30),len(slots)):
       slots[i]=SLOT_RATE
     for i in range(math.ceil(endMinutes/30)):
       slots[i]=SLOT_RATE
   else:
     for i in range(math.floor(startMinutes/30),math.ceil(endMinutes/30)):
       slots[i]=SLOT_RATE


def getTimes():
    object = getObject()
    return object['plannedDispatches']

def returnPartnerSlotStart(startTime):
    for x in times:
        slotStart = datetime.strptime(x['startDt'],'%Y-%m-%d %H:%M:%S%z')
        slotEnd = datetime.strptime(x['endDt'],'%Y-%m-%d %H:%M:%S%z')
        if(startTime == slotEnd):
            return slotEnd

def returnPartnerSlotEnd(endTime):
    for x in times:
        slotStart = datetime.strptime(x['startDt'],'%Y-%m-%d %H:%M:%S%z')
        slotEnd = datetime.strptime(x['endDt'],'%Y-%m-%d %H:%M:%S%z')
        if(endTime == slotStart):
            return slotEnd

#Get Token
authToken = refreshToken(apikey,accountNumber)
times = getTimes()

# Get savings session - assume only 1 per day
eventStart, eventEnd, exportPrice=fn_savings_sessions.saving_sessions(octopusURL,authToken,accountNumber)
if DEBUG:
  print("Saving Session Data: "+str(eventStart)+" -> "+str(eventEnd)+" @ £"+str(exportPrice)+"/kwh\n")

# Set export rate & import rate to the same - powerwall doesn't support export rates higher than import
SAVINGS_EXPORT_RATE = SAVINGS_RATE = exportPrice

#Convert to the current timezone
for i,time in enumerate(times):
    slotStart = datetime.strptime(time['startDt'],'%Y-%m-%d %H:%M:%S%z').astimezone(ZoneInfo("Europe/London"))
    slotEnd = datetime.strptime(time['endDt'],'%Y-%m-%d %H:%M:%S%z').astimezone(ZoneInfo("Europe/London"))
    time['startDt'] = str(slotStart)
    time['fromHour'] = str(slotStart.hour)
    time['fromMinute'] = str(slotStart.minute)
    time['endDt'] = str(slotEnd)
    time['toHour'] = str(slotEnd.hour)
    time['toMinute'] = str(slotEnd.minute)
    time['fromDayOfWeek'] = 0
    time['toDayOfWeek'] = 6
    times[i] = time

timeNow = datetime.now(timezone.utc).astimezone()

#if(ENABLE_PRECONDITION and len(times)!=0):
#   Precondition.preCondition(timeNow,times)

#Santise Times
#Remove times within 23:30-05:30 slots
newTimes = []
addExtraSlot = True
for i,time in enumerate(times):
    slotStart = datetime.strptime(time['startDt'],'%Y-%m-%d %H:%M:%S%z').astimezone()
    slotEnd = datetime.strptime(time['endDt'],'%Y-%m-%d %H:%M:%S%z').astimezone()
#    print("Octopus Slots: "+str(slotStart)+' -> '+str(slotEnd)+' ---- '+str(ioStart)+' - '+str(ioEnd))
    if(not((ioStart <= slotStart <= ioEnd) and (ioStart <= slotEnd <= ioEnd))):
        if((slotStart <= ioStart) and (ioStart < slotEnd <= ioEnd)):
            time['endDt'] = str(ioStart)
            time['toHour'] = str(ioStart.hour)
            time['toMinute'] = str(ioStart.minute)
            times[i] = time
        if((ioStart <= slotStart <= ioEnd) and (ioEnd < slotEnd)):
            time['startDt'] = str(ioEnd)
            time['fromHour'] = str(ioEnd.hour)
            time['fromMinute'] = str(ioEnd.minute)
        newTimes.append(time)
    if((slotStart <= ioStart <= slotEnd) and (slotStart <= ioEnd <= slotEnd)):
        #This slot overlaps our IO slot - we need not add it manually at the next step
        addExtraSlot = False
times = newTimes
if DEBUG:
  print("All Slots: "+str(times))
if(addExtraSlot):
    #Add our IO period
    ioPeriod = json.loads('[{"fromDayOfWeek": 0,"toDayOfWeek" : 6,"fromHour" : '+str(ioStart.hour)+', "fromMinute":'+str(ioStart.minute)+', "toHour":'+ str(ioEnd.hour)+', "toMinute":'+str(ioEnd.minute)+',"startDt":"'+str(ioStart)+'","endDt":"'+str(ioEnd)+'"\n}]')
    times.extend(ioPeriod)
    times.sort(key=lambda x: x['startDt'])

newTimes = []
#Any partner slots a.k.a. slots next to each other
for i,time in enumerate(times):
    while True:
        slotStart = datetime.strptime(time['startDt'],'%Y-%m-%d %H:%M:%S%z').astimezone()
        slotEnd = datetime.strptime(time['endDt'],'%Y-%m-%d %H:%M:%S%z').astimezone()
        if((i+1)<len(times)):
            partnerStart = datetime.strptime(times[i+1]['startDt'],'%Y-%m-%d %H:%M:%S%z').hour
            partnerStartMin = datetime.strptime(times[i+1]['startDt'],'%Y-%m-%d %H:%M:%S%z').minute
            partnerEnd = datetime.strptime(times[i+1]['endDt'],'%Y-%m-%d %H:%M:%S%z').hour
            partnerEndMin = datetime.strptime(times[i+1]['endDt'],'%Y-%m-%d %H:%M:%S%z').minute
            if(slotEnd == partnerStart):
                times.pop((i+1))
                time['endDt'] = str(partnerEnd)
                times[i] = time
            else:
                break
        else:
            break

newTimes = []
#Any slots in the past
for i,time in enumerate(times):
    slotStart = datetime.strptime(time['startDt'],'%Y-%m-%d %H:%M:%S%z').astimezone()
    slotStartHour = datetime.strptime(time['startDt'],'%Y-%m-%d %H:%M:%S%z').hour
    slotStartMinute = datetime.strptime(time['startDt'],'%Y-%m-%d %H:%M:%S%z').minute
    slotEnd = datetime.strptime(time['endDt'],'%Y-%m-%d %H:%M:%S%z').astimezone()
    slotEndHour = datetime.strptime(time['endDt'],'%Y-%m-%d %H:%M:%S%z').hour
    slotEndMinute = datetime.strptime(time['endDt'],'%Y-%m-%d %H:%M:%S%z').minute
    if(not(slotStart <= timeNow and slotEnd <= timeNow)):
        newTimes.append(time)
times = newTimes

# Create slot array - each item represents a 30 min slot from 0:00 to 23:30 to be populated with offpeak or onpeak slots. Initialise with all on-peak
slots=[2]*48

#Add the default off-peak period
#for i in range(int(ioEnd.hour)*2+int(math.ceil(int(ioEnd.minute)/30))):
#  slots[i]=SLOT_OFFPEAK
#for i in range((int(ioStart.hour)*2+int(math.ceil(int(ioStart.minute)/30))),len(slots)):
#  slots[i]=SLOT_OFFPEAK
#print(slots)
fillSlots(SLOT_OFFPEAK, ioStart, ioEnd)
for entry in times:
  fillSlots(SLOT_OFFPEAK, datetime.strptime(entry['startDt'],'%Y-%m-%d %H:%M:%S%z'), datetime.strptime(entry['endDt'],'%Y-%m-%d %H:%M:%S%z'))

#fillSlots(SLOT_OFFPEAK, datetime.strptime("2024-11-17 21:30:00",'%Y-%m-%d %H:%M:%S'), datetime.strptime("2024-11-17 23:30:00",'%Y-%m-%d %H:%M:%S'))
#fillSlots(SLOT_OFFPEAK, datetime.strptime("2024-11-17 06:00:00",'%Y-%m-%d %H:%M:%S'), datetime.strptime("2024-11-17 10:30:00",'%Y-%m-%d %H:%M:%S'))
#fillSlots(SLOT_FREE, datetime.strptime("2024-11-17 13:00:00",'%Y-%m-%d %H:%M:%S'), datetime.strptime("2024-11-17 14:00:00",'%Y-%m-%d %H:%M:%S'))
#fillSlots(SLOT_SAVINGS, datetime.strptime("2024-11-17 17:30:00",'%Y-%m-%d %H:%M:%S'), datetime.strptime("2024-11-17 18:30:00",'%Y-%m-%d %H:%M:%S'))

# If we have a valid savings event, and the rate offered is greater than the current onpeak rate + offset, then add the slot
if(eventStart!=0 and eventEnd!=0 and export_rate>ONPEAK_SELL_RATE+SAVINGS_MIN_OFFSET and PARTICIPATE_SAVING_SESSIONS):
  fillSlots(SLOT_SAVINGS, eventStart, eventEnd)

freeStart, freeEnd = check_free_electricity.freeElectric()
if(PARTICIPATE_FREE_ELECTRIC and freeEnd.astimezone(ZoneInfo("Europe/London"))>dateTimeToUse  and (freeEnd.day==dateTimeToUse.day and freeEnd.month==dateTimeToUse.month)):
  fillSlots(SLOT_FREE, freeStart, freeEnd)

outputJson = ""
onPeakJson = ""
freeJson = ""
savingsJson = ""

# populates the different JSON strings
def writeJSON(slotType,start,end):
#   print("Slot Type: "+str(slotType)+" Slot Start: "+str((start)/2)+" Slot End: "+str((end)/2))
   global outputJson
   global onPeakJson
   global freeJson
   global savingsJson
   slotString=""

   startHour = math.floor(start/2)
   if((start/2).is_integer()):
     startMinute=0
   else:
     startMinute=30
   if((end/2).is_integer()):
     endHour = math.floor(end/2)
     endMinute = 0
   else:
     endHour = math.floor(end/2)
     endMinute = 30
#   if(i==len(slots)):
#     endHour=0
#     endMinute=0
   if(int(slotType)==int(SLOT_OFFPEAK)):
     outputJson = outputJson + '                   {\n                   "fromDayOfWeek": 0,\n                   "toDayOfWeek": 6,\n                   "fromHour":'+str(startHour)+',\n                   "fromMinute":'+str(startMinute)+',\n                   "toHour":'+str(endHour)+',\n                   "toMinute":'+str(endMinute)+'\n                   },\n'
     slotString = "Off Peak"
   elif(slotType==SLOT_ONPEAK):
     onPeakJson = onPeakJson + '                   {\n                   "fromDayOfWeek": 0,\n                   "toDayOfWeek": 6,\n                   "fromHour":'+str(startHour)+',\n                   "fromMinute":'+str(startMinute)+',\n                   "toHour":'+str(endHour)+',\n                   "toMinute":'+str(endMinute)+'\n                   },\n'
     slotString = "On Peak"
   elif(slotType==SLOT_FREE):
     freeJson = freeJson + '                   {\n                   "fromDayOfWeek": 0,\n                   "toDayOfWeek": 6,\n                   "fromHour":'+str(startHour)+',\n                   "fromMinute":'+str(startMinute)+',\n                   "toHour":'+str(endHour)+',\n                   "toMinute":'+str(endMinute)+'\n                   },\n'
     slotString = "Free Session"
   elif(slotType==SLOT_SAVINGS):
     savingsJson = savingsJson + '                   {\n                   "fromDayOfWeek": 0,\n                   "toDayOfWeek": 6,\n                   "fromHour":'+str(startHour)+',\n                   "fromMinute":'+str(startMinute)+',\n                   "toHour":'+str(endHour)+',\n                   "toMinute":'+str(endMinute)+'\n                   },\n'
     slotString = "Saving Session"

#  Print out the string that lets the user know what slots we have
   print(slotString+" -- "+str(startHour)+":"+str(startMinute)+" -> "+str(endHour)+":"+str(endMinute))

i=0
if DEBUG:
  print("All Slot Allocations: "+str(slots))
for i in range(len(slots)):
  # Holds a pointer to the start of the slot 
  if(i==0):
    slotStartRef=i
#  print(slotStartRef, slots[i])
  if(slots[i]!=slots[slotStartRef]):
    writeJSON(slots[slotStartRef], slotStartRef,i)
    slotStartRef=i
  if(i==len(slots)-1):
    writeJSON(slots[slotStartRef], slotStartRef, 0)

if DEBUG:
  print("-------------------------------------------\n")
  print("Off Peak:\n")
  print(outputJson)
  print("----------------\n")
  print("On Peak:\n")
  print(onPeakJson)
  print("----------------\n")
  print("Free Electricity:\n")
  print(freeJson)
  print("----------------\n")
  print("Savings Session:\n")
  print(savingsJson)
  print("-------------------------------------------\n")

# trim the comma from the end of the last part of the string
outputJson = outputJson[:-2]+"\n"
onPeakJson = onPeakJson[:-2]+"\n"
freeJson = freeJson[:-2]+"\n"
savingsJson = savingsJson[:-2]+"\n"

outputJsonContent = json.dumps(outputJson, indent=4, default=str)

OctopusOffPeakTimeSlot = ""
OctopusOnPeakTimeSlot = ""
OctopusFreeTimeSlot = ""
OctopusSavingsTimeSlot = ""

# Add the start and end text to the sections
OctopusOffPeakTimeSlot = OctopusOffPeakTimeSlotBaseStart + outputJson + OctopusOffPeakTimeSlotBaseEnd
OctopusOnPeakTimeSlot = OctopusOnPeakTimeSlotBaseStart + onPeakJson + OctopusOnPeakTimeSlotBaseEnd
# If there's a free electricity day or savings day, we need to add the comma for the next section
# We assume free electricity will never happen on the same day as savings
if(freeJson!="\n" or savingsJson!="\n"):
  OctopusOnPeakTimeSlot = OctopusOnPeakTimeSlot[:-1] + ",\n"

# If there's a free electricity session or savings session, add the start and end text
if(freeJson!="\n"):
  OctopusFreeTimeSlot = OctopusFreeTimeSlotBaseStart + freeJson + OctopusFreeTimeSlotBaseEnd
if(savingsJson!="\n"):
  OctopusSavingsTimeSlot = OctopusSavingsTimeSlotBaseStart + savingsJson + OctopusSavingsTimeSlotBaseEnd

if DEBUG:
   print("Octopus Off-Peak Time Slot JSON: \n"+OctopusOffPeakTimeSlot)
   print("Octopus On-peak Time Slot JSON: \n"+OctopusOnPeakTimeSlot)
   print("Octopus Free Time Slot JSON: \n"+OctopusFreeTimeSlot)
   print("Octopus Savings Time Slot JSON: \n"+OctopusSavingsTimeSlot)

def sendData(teslasiteid,tessieapikey,teslaurl,OctopusTimeSlot):
    try:
#       Build query 
        query1 = """
      "code": "(edited)",
      "name": "Intelligent Octopus Go",
      "utility": "Octopus",
      "daily_charges": [
        {
          "name": "Charge"
        }
      ],
      "demand_charges": {
        "ALL": {
          "rates": {
            "ALL": 0
          }
        },
        "Summer": {},
        "Winter": {}
      },
      "energy_charges": {
        "ALL": {
          "rates": {
            "ALL": 0
          }
        },
        "Summer": {
          "rates": {
            "OFF_PEAK": """+str(OFFPEAK_RATE)+""",
            "ON_PEAK": """+str(ONPEAK_RATE)+""",
            "SUPER_OFF_PEAK": """+str(FREE_RATE)+""",
            "MID_PEAK": """+str(SAVINGS_RATE)+"""
          }
        },
        "Winter": {}
      },
      "seasons": {
        "Summer": {
          "fromDay": 1,
          "toDay": 31,
          "fromMonth": 1,
          "toMonth": 12,
          "tou_periods": { """

        query2 =  """          }
        },
        "Winter": {}
      },
      "sell_tariff": {
        "name": "Intelligent Octopus Go",
        "utility": "Octopus",
        "daily_charges": [
          {
            "name": "Charge"
          }
        ],
        "demand_charges": {
          "ALL": {
            "rates": {
              "ALL": 0
            }
          },
          "Summer": {},
          "Winter": {}
        },
        "energy_charges": {
          "ALL": {
            "rates": {
              "ALL": 0
            }
          },
          "Summer": {
            "rates": {
              "OFF_PEAK": """+str(OFFPEAK_SELL_RATE)+""",
              "ON_PEAK": """+str(ONPEAK_SELL_RATE)+""",
              "SUPER_OFF_PEAK": """+str(FREE_RATE)+""",
              "MID_PEAK": """+str(SAVINGS_RATE)+"""
            }
          },
          "Winter": {}
        },
        "seasons": {
          "Summer": {
            "fromDay": 1,
            "toDay": 31,
            "fromMonth": 1,
            "toMonth": 12,
            "tou_periods": {  """

        query3 = """            }
          },
          "Winter": {}
        }
      },
      "version": 1
      }
        """
        fullquery = "{\n \"tou_settings\": {\n \"tariff_content_v2\": {"+query1+OctopusTimeSlot+query2+OctopusTimeSlot+query3+"\n}\n }"
        if DEBUG:
           print("Powerwall Schedule Update Query: \n"+fullquery)
        headers={"Content-Type": "application/json","Authorization": "Bearer "+tessieapikey}
        if DEBUG:
           print("Headers: "+headers)
           print("Powerwall Update URL: "+teslaurl)
        if not READONLY:
           r = requests.post(teslaurl,fullquery,headers=headers)
           print(f'HTTP Error {r.status_code}') 
           print(f'HTTP Message {r.reason}')
#           print("Result: "+json.loads(r.text)['data'])
           if(int(r.status_code) == 200):
              LogMsg("INFO","Successfully updated Tesla Powerwall schedule")
              # Update the IO changed hash file with the latest hash
              f = open("IO-Changed-Hash","w")
              f.write(newHash)
              f.close()
              if DEBUG:
                print("Updated new hash into changed hash file: "+newHash)
           else:
              LogMsg("ERROR","Failed to update Tesla Powerwall API. Code: "+r.status_code+" - Message: "+r.reason)
           return json.loads(r.text)['data']
    except HTTPError as http_err:
        print(f'HTTP Error {http_err}')
    except Exception as err:
        print(f'Another error occurred: {err}')

# Create the new hash based on our timeslot data
newHash = OctopusOffPeakTimeSlot+OctopusOnPeakTimeSlot+OctopusFreeTimeSlot+OctopusSavingsTimeSlot
newHash = str(hashlib.sha256(newHash.encode()).hexdigest())
if DEBUG:
   print("Old Hash: >"+changedHash+"<\n")
   print("New Hash: >"+newHash+"<\n")
# If there has been a change in the slots, we will update the Tesla API. 
if changedHash != newHash or FORCEUPDATE:
   if DEBUG:
      print("Change in slots, update the Tesla API")
      LogMsg("DEBUG","Change in slots, update the Tesla API")
   sendData(teslasiteid,tessieapikey,teslaurl,OctopusOffPeakTimeSlot+OctopusOnPeakTimeSlot+OctopusFreeTimeSlot+OctopusSavingsTimeSlot)
else:
   print("No change in slots. Do nothing")
   if DEBUG:
     LogMsg("DEBUG","No change in slots. Do nothing")

