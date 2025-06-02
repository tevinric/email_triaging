import os

# IMPORTS 

from config import POLICY_SERVICES, TRACKING_MAILS, CLAIMS_MAILS, ONLINESUPPORT_MAILS, INSURANCEADMIN_MAILS, DIGITALCOMMS_MAILS, CONNEX_TEST

# ROUTINGS

ang_routings = {
    # Ammendments
    "amendments"                :   POLICY_SERVICES,
    "assist"                    :   POLICY_SERVICES,
    "vehicle tracking"          :   TRACKING_MAILS,
    "bad service/experience"    :   POLICY_SERVICES,
    "claims"                    :   CLAIMS_MAILS,
    "refund request"            :   POLICY_SERVICES,
    "document request"          :   ONLINESUPPORT_MAILS,
    "online/app"                :   ONLINESUPPORT_MAILS,
    "retentions"                :   DIGITALCOMMS_MAILS,
    "request for quote"         :   POLICY_SERVICES,
    "debit order switch"        :   ONLINESUPPORT_MAILS,
    "previous insurance checks/queries" : INSURANCEADMIN_MAILS,
    "other"                     :   POLICY_SERVICES,
}
