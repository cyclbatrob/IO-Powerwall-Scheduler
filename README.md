# -----------------------------
#   IO-Powerwall-Scheduler
# -----------------------------

Manages the Powerwall tariff based on Intelligent Octopus slot times

IO Powerwall Scheduler manages the tariff schedule within the Powerwall configuration for Intelligent Octopus customers by creating JSON which is fed into the Tesla API. The script takes the planned charging slots from Octopus and creates an appropriate tariff schedule to ensure the Powerwall knows they are off-peak. The script is also able to take account of free electricity sessions. Savings sessions are within the code but are not enabled by default due to lack of testing. 

At this time, a Tessie API key is required to update the Tesla API, and an Octopus API key is required to access the Intelligent Octopus slots. 

# -----------------------------
# Installation
# -----------------------------
 - Clone or download the files into a single directory
 - Execute IO-Update-Powerwall-Shedule-vX.X.py to build the config file
 - Add your Tessie API key to the config file
 - Execute Get-SiteID.py to get your Tesla site ID
 - Add your Octopus API key and Account Number into the config file
 - Use a task scheduler - eg Cron on Linux - to schedule the script execution - recommend every 1 minute

# -----------------------------
# Running the script
# -----------------------------
There are 3 core files to the solution, IO-Update-Powerwall-Schedule-vX.X.py, check_free_electricity.py and fn_savings_sessions.py. The only one that should be executed is IO-Update-Powerwall-Schedule-vX.X.py

There is also a Get-SiteID.py script - this is a 1-off script to get your site ID from Tesla.

On first run, IO-Update-Powerwall-Schedule-vX.X.py will create the config file - config.txt with a set of defaults. It MUST be edited with a minimum of the Tessie API key, Tesla Site ID, Octopus API key and Octopus account number.

The script is designed to run with Python3 and needs to be scheduled to run regularly - it is known to work well using a Cron job on Linux, but can probably also be run using task scheduler on Windows. Executing the script every minute will provide the most responsive solution - for the times when Intelligent Octopus gives an immediate time slot when plugging the car in.


# -----------------------------
# Config File
# -----------------------------
A default config file is created when the script is run for the first time or a valid config file is not detected. It is possible to have multiple config files to manage multiple Octopus accounts and Powerwall installations - if this is required then the config file is fed in as a command line argument.

The config file contains all the config required for the script and is broken down into sections. As a MINIMUM, the following MUST be configured to enable the script to run:
 - TESSIE_API_KEY - can be found in the Tessie App under Settings -> Developer API
 - TESLA_Site_ID - is found by running Get-SiteID.py once the Tessie API key is configured in the config file.
 - OCTOPUS_API_KEY - can be found in the Octopus account section in octopus.energy
 - OCTOPUS_ACCOUNT_NUMBER - can be found in the Octopus account section in octopus.energy

Other configuration options: 
 - FREE_ELECTRIC - Set to True or False to take part in free electricity sessions
 - SAVINGS_SESSIONS - NOT TESTED!!! Set to True or False to take part in Octopus Savings sessions. In late 2024, the only Octopus saving session so far didn't appear in the API so further testing is required.
 - Tariff Rates - adjust as necessary. Tesla gets really confused if export rate is higher than import, so keep it as the same or just below.
 - SAVINGS_MIN_OFFSET - for savings sessions, how much £ per Kw ABOVE the standard rate before participating. Default is 0
 - DEBUG - for debugging
 - READONLY - will not update the Tesla API - for debugging
 - FORCE_UPDATE - ignores the hash file
 - Powerwall-Limit-Export options - unused within this script but is for a separate tool
 - MQTT Options - used to enable or disable the script by MQTT subscription. Disabled by default

# -----------------------------
# Logging
# -----------------------------
Upon execution, a log file - IO-Update-Powerwall-Schedule.log - is created. In debug mode this gives more info, as well as output to the screen. In standard mode, it only adds to the log when anything has changed or errored.

# -----------------------------
# Hash File
# -----------------------------
To avoid updating the Tesla API every minute, a hash file is used to retain the fingerprint of the last update made by the script. If the hash remains the same, then the API to update the tariff is not called. Updates made via other means are not detected. To ignore the hash file and force an update, use the setting FORCE_UPDATE = True
