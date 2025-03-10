import os

# IMPORTS 

POLICY_SERVICES=os.environ.get('POLICY_SERVICES')
TRACKING_MAILS=os.environ.get('TRACKING_MAILS')
CLAIMS_MAILS=os.environ.get('CLAIMS_MAILS')
ONLINESUPPORT_MAILS=os.environ.get('ONLINESUPPORT_MAILS')
INSURANCEADMIN_MAILS=os.environ.get('INSURANCEADMIN_MAILS')
DIGITALCOMMS_MAILS=os.environ.get('DIGITALCOMMS_MAILS')
CONNEX_TEST=os.environ.get('CONNEX_TEST')

# ROUTINGS

ang_routings = {
    # Ammendments
    "amendments"                :   POLICY_SERVICES,
    "assist"                    :   POLICY_SERVICES,
    #"vehicle"                   :   POLICY_SERVICES,
    "vehicle tracking"          :   TRACKING_MAILS,
    #"buildings"                 :   POLICY_SERVICES,
    #"home contents"             :   POLICY_SERVICES,
    #"portable possessions"      :   POLICY_SERVICES,
    #"split risk"                :   POLICY_SERVICES,
    "bad service/experience"    :   POLICY_SERVICES,
    "claims"                    :   CLAIMS_MAILS,
    "refund request"            :   POLICY_SERVICES,
    "document request"          :   ONLINESUPPORT_MAILS,
    "online/app"                :   ONLINESUPPORT_MAILS,
    "retentions"                :   DIGITALCOMMS_MAILS,
    "request for quote"         :   POLICY_SERVICES,
    "debit order switch"        :   ONLINESUPPORT_MAILS,
    "previous insurance checks/queries" : INSURANCEADMIN_MAILS,
    "connex test"               :   CONNEX_TEST,
    "other"                     :   POLICY_SERVICES,
}
