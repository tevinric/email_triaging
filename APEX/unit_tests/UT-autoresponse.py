import re

##########################################################################################################################################################

#UNIT TEST SUITE 1 - NOT SENDER EMAIL ADDRESS


UNIT_TEST_1_COUNT = 3
UNIT_TEST_1_PASSED = 0

def ut11_no_sender():
    UT1_TEST_SUBJECT = 'Unit test1'

    ## UNIT TEST 1 (UT1) - Variant 1 (No sender in the email details)
    UT11_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'to': 'test@tester',  # This now contains the corrected TO address for bounces
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT1_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    sender_email = UT11_email_details.get('from')
    
    if not sender_email or sender_email==None or sender_email=='' or len(sender_email.strip())<5:
        reason = "No sender email found"
        
        return True, reason

ut11_outcome, ut11_reason = ut11_no_sender()

if ut11_outcome==True:
    UNIT_TEST_1_PASSED += 1
    print(f"UT 11 - NO SENDER TEST PASSED: {ut11_reason}")
else:
    print(f"UT 11 - NO SENDER TEST FAILED: Investigate the issue")


def ut12_no_sender():
    UT1_TEST_SUBJECT = 'Unit test1'

    ## UNIT TEST 1 (UT1) - Variant 1 (No sender in the email details)
    UT12_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'to': 'test@tester',  # This now contains the corrected TO address for bounces
        'from': None,
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT1_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    sender_email = UT12_email_details.get('from')
    
    if not sender_email or sender_email==None or sender_email=='' or len(sender_email.strip())<5:
        reason = "No sender email found"
        return True, reason

ut12_outcome, ut12_reason = ut12_no_sender()

if ut12_outcome==True:
    UNIT_TEST_1_PASSED += 1
    print(f"UT 12 - NO SENDER TEST PASSED: {ut12_reason}")
else:
    print(f"UT 12 - NO SENDER TEST FAILED: Investigate the issue")

def ut13_no_sender():
    UT1_TEST_SUBJECT = 'Unit test1'

    ## UNIT TEST 1 (UT1) - Variant 1 (No sender in the email details)
    UT13_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'to': 'test@tester',  # This now contains the corrected TO address for bounces
        'from': '',
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT1_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    sender_email = UT13_email_details.get('from')

    if not sender_email or sender_email==None or sender_email=='' or len(sender_email.strip())<5:
        reason = "No sender email found"
        return True, reason

ut13_outcome, ut13_reason = ut13_no_sender()

if ut13_outcome==True:
    UNIT_TEST_1_PASSED += 1
    print(f"UT 13 - NO SENDER TEST PASSED: {ut13_reason}")
else:
    print(f"UT 13 - NO SENDER TEST FAILED: Investigate the issue")


print(f"Unit tests for UT1 completed, Total UT1 tests: {UNIT_TEST_1_COUNT}, Passed: {UNIT_TEST_1_PASSED}, Failed: {UNIT_TEST_1_COUNT - UNIT_TEST_1_PASSED}")

##########################################################################################################################################################


#UNIT TEST SUITE 2 - NOT RECIPENT EMAIL ADDRESS specified
UNIT_TEST_2_COUNT = 3
UNIT_TEST_2_PASSED = 0


# MISSING RECIPIENT 
def ut21_no_recipient():
    UT2_TEST_SUBJECT = 'Unit test2'

    ## UNIT TEST 2 (UT2) - Variant 1 (No recipient in the email details)
    UT21_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'from': 'test@tester.com',
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT2_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    recipient_email = UT21_email_details.get('to')

    if not recipient_email or recipient_email==None or recipient_email=='' or len(recipient_email.strip())<5:
        reason = "No recipient email found"
        return True, reason

ut21_outcome, ut21_reason = ut21_no_recipient()

if ut21_outcome==True:
    UNIT_TEST_2_PASSED += 1
    
    print(f"UT 21 - NO RECIPIENT TEST PASSED: {ut21_reason}")
else:
    print(f"UT 21 - NO RECIPIENT TEST FAILED: Investigate the issue")


# MISSING RECIPIENT 
def ut22_no_recipient():
    UT2_TEST_SUBJECT = 'Unit test2'

    ## UNIT TEST 2 (UT2) - Variant 2 (No recipient in the email details)
    UT22_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'from': 'test@tester.com',
        'to': None,  # This now contains the corrected TO address for bounces
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT2_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    recipient_email = UT22_email_details.get('to')

    if not recipient_email or recipient_email==None or recipient_email=='' or len(recipient_email.strip())<5:
        reason = "No recipient email found"
        return True, reason

ut22_outcome, ut22_reason = ut22_no_recipient()

if ut22_outcome==True:
    UNIT_TEST_2_PASSED += 1

    print(f"UT 22 - NO RECIPIENT TEST PASSED: {ut22_reason}")
else:
    print(f"UT 22 - NO RECIPIENT TEST FAILED: Investigate the issue")


# RECIPIENT IS NONE
def ut23_no_recipient():
    UT2_TEST_SUBJECT = 'Unit test2'

    ## UNIT TEST 2 (UT2) - Variant 1 (No recipient in the email details)
    UT23_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'to': '',  # This now contains the corrected TO address for bounces
        'from': 'test@tester.com',
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT2_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    recipient_email = UT23_email_details.get('to')

    if not recipient_email or recipient_email==None or recipient_email=='' or len(recipient_email.strip())<5:
        reason = "No recipient email found - None"
        return True, reason

ut23_outcome, ut23_reason = ut23_no_recipient()

if ut23_outcome==True:
    UNIT_TEST_2_PASSED += 1

    print(f"UT 23 - NO RECIPIENT TEST PASSED: {ut23_reason}")
else:
    print(f"UT 23 - NO RECIPIENT TEST FAILED: Investigate the issue")


print(f"Unit tests for UT2 completed, Total UT2 tests: {UNIT_TEST_2_COUNT}, Passed: {UNIT_TEST_2_PASSED}, Failed: {UNIT_TEST_2_COUNT - UNIT_TEST_2_PASSED}")

##########################################################################################################################################################

#UNIT TEST SUITE 3 - PRIMARY LOOP PREVENTION - SKIP IF EMAIL WAS SENT TO ANY AUTORESPONSE ACCOUNT
UNIT_TEST_3_COUNT = 1
UNIT_TEST_3_PASSED = 0

def ut31_primary_loop_prevention():
    UT2_TEST_SUBJECT = 'Unit test3'

    EMAIL_ACCOUNTS = ['insuranservices@autogen.co.za']

    ## UNIT TEST 3 (UT3) - Variant 1 (No recipient in the email details)
    UT31_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'to': 'insuranservices@autogen.co.za',  # This now contains the corrected TO address for bounces
        'from': 'test@tester.com',
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT2_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    #GET THE DETAILS FROM THE EMAIL HEADER
    sender_email = UT31_email_details.get('from')
    recipient_email = UT31_email_details.get('to')
    
    
    # CLEAN THE SENDER AND RECIPIENT EMAILS
    sender_clean = sender_email.lower().strip()
    recipient_clean = recipient_email.lower().strip()


    if EMAIL_ACCOUNTS:
        for account in EMAIL_ACCOUNTS:
            if account:
                account_clean = account.lower().strip()

                # CHECKING -> Was the email sent to the autoresponse account/ consolidation bin?
                if recipient_clean == account_clean:
                    reason = f"Email sent directly to autoresponse account: {recipient_email}"
                    return True, reason

ut31_outcome, ut31_reason = ut31_primary_loop_prevention()

if ut31_outcome==True:
    UNIT_TEST_3_PASSED += 1

    print(f"UT 31 - PRIMARY LOOP PREVENTION TEST PASSED: {ut31_reason}")
else:
    print(f"UT 31 - PRIMARY LOOP PREVENTION TEST FAILED: Investigate the issue")


print(f"Unit tests for UT3 completed, Total UT3 tests: {UNIT_TEST_3_COUNT}, Passed: {UNIT_TEST_3_PASSED}, Failed: {UNIT_TEST_3_COUNT - UNIT_TEST_3_PASSED}")


##########################################################################################################################################################

#UNIT TEST SUITE 4 - SECONDARY LOOP PREVENTION - Skip if sender is also an autoresponse account. Prevention against self initiated loops
UNIT_TEST_4_COUNT = 1
UNIT_TEST_4_PASSED = 0

def ut41_secondary_loop_prevention():
    UT2_TEST_SUBJECT = 'Unit test4'

    EMAIL_ACCOUNTS = ['insuranservices@autogen.co.za']

    ## UNIT TEST 4 (UT4) - Variant 1 (No recipient in the email details)
    UT41_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'to': 'insuranservices@autogen.co.za',  # This now contains the corrected TO address for bounces
        'from': 'insuranservices@autogen.co.za',
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT2_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    #GET THE DETAILS FROM THE EMAIL HEADER
    sender_email = UT41_email_details.get('from')
    recipient_email = UT41_email_details.get('to')


    # CLEAN THE SENDER AND RECIPIENT EMAILS
    sender_clean = sender_email.lower().strip()
    recipient_clean = recipient_email.lower().strip()


    if EMAIL_ACCOUNTS:
        for account in EMAIL_ACCOUNTS:
            if account:
                account_clean = account.lower().strip()
                if sender_clean == account_clean:
                    reason = f"Sender is also an autoresponse account: {sender_email}"
                    return True, reason

ut41_outcome, ut41_reason = ut41_secondary_loop_prevention()

if ut41_outcome==True:
    UNIT_TEST_4_PASSED += 1

    print(f"UT 41 - SECONDARY LOOP PREVENTION TEST PASSED: {ut41_reason}")
else:
    print(f"UT 41 - SECONDARY LOOP PREVENTION TEST FAILED: Investigate the issue")


print(f"Unit tests for UT4 completed, Total UT4 tests: {UNIT_TEST_4_COUNT}, Passed: {UNIT_TEST_4_PASSED}, Failed: {UNIT_TEST_4_COUNT - UNIT_TEST_4_PASSED}")


##########################################################################################################################################################

#UNIT TEST SUITE 5 - MICROSOFT EXCHANGE SYSTEM DETECTION - Primary defense against bounce loops
UNIT_TEST_5_COUNT = 2
UNIT_TEST_5_PASSED = 0

def ut51_microsoft_exchange_detection():
    UT5_TEST_SUBJECT = 'Unit test5'

    EMAIL_ACCOUNTS = ['insuranservices@autogen.co.za']

    ## UNIT TEST 5 (UT5) - Variant 1 STANDARD EXHANGE PATTERN
    UT51_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'to': 'insuranservices@autogen.co.za',  # This now contains the corrected TO address for bounces
        'from': 'MicrosoftExchange329e71ec88ae4615bbc36ab6ce41109e@telesure.co.za',
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT5_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    #GET THE DETAILS FROM THE EMAIL HEADER
    sender_email = UT51_email_details.get('from')
    recipient_email = UT51_email_details.get('to')


    # CLEAN THE SENDER AND RECIPIENT EMAILS
    sender_clean = sender_email.lower().strip()
    recipient_clean = recipient_email.lower().strip()

    exchange_patterns = [
        r'microsoftexchange[a-f0-9]+@',  # Standard Exchange pattern
        r'exchange[a-f0-9]+@',          # Alternative Exchange pattern
        r'[a-f0-9]{32}@'                # Generic 32-character hex @ domain
    ]
    
    for pattern in exchange_patterns:
        if re.search(pattern, sender_clean):
            reason = f"Microsoft Exchange system sender detected: {sender_email} (matches pattern '{pattern}')"
            return True, reason

ut51_outcome, ut51_reason = ut51_microsoft_exchange_detection()

if ut51_outcome==True:
    UNIT_TEST_5_PASSED += 1

    print(f"UT 51 - MICROSOFT EXCHANGE DETECTION TEST PASSED: {ut51_reason}")
else:
    print(f"UT 51 - MICROSOFT EXCHANGE DETECTION TEST FAILED: Investigate the issue")


def ut52_microsoft_exchange_detection():
    UT5_TEST_SUBJECT = 'Unit test5'

    ## UNIT TEST 5 (UT5) - Variant 1 STANDARD EXHANGE PATTERN
    ut52_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'to': 'insuranservices@autogen.co.za',  # This now contains the corrected TO address for bounces
        'from': 'MicrosoftExchange329e71ec88ae4615bbc36ab6ce4110fe@telesure.co.za', #RANDOM CREATED
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT5_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    #GET THE DETAILS FROM THE EMAIL HEADER
    sender_email = ut52_email_details.get('from')
    recipient_email = ut52_email_details.get('to')


    # CLEAN THE SENDER EMAIL
    sender_clean = sender_email.lower().strip()

    exchange_patterns = [
        r'microsoftexchange[a-f0-9]+@',  # Standard Exchange pattern
        r'exchange[a-f0-9]+@',          # Alternative Exchange pattern
        r'[a-f0-9]{32}@'                # Generic 32-character hex @ domain
    ]
    
    for pattern in exchange_patterns:
        if re.search(pattern, sender_clean):
            reason = f"Microsoft Exchange system sender detected: {sender_email} (matches pattern '{pattern}')"
            return True, reason

        else:
            return False, "No Microsoft Exchange system sender detected"

ut52_outcome, ut52_reason = ut52_microsoft_exchange_detection()

if ut52_outcome==True:
    UNIT_TEST_5_PASSED += 1
    print(f"UT 52 - MICROSOFT EXCHANGE DETECTION TEST PASSED: {ut52_reason}")
else:
    print(f"UT 52 - MICROSOFT EXCHANGE DETECTION TEST FAILED: {ut52_reason}")


print(f"Unit tests for UT5 completed, Total UT5 tests: {UNIT_TEST_5_COUNT}, Passed: {UNIT_TEST_5_PASSED}, Failed: {UNIT_TEST_5_COUNT - UNIT_TEST_5_PASSED}")


##########################################################################################################################################################

#UNIT TEST SUITE 6 - CHECKING FOR DOMAIN SPECIFIC SUBSTRINGS IN SENDER EMAIL ADDRESS
UNIT_TEST_6_COUNT = 1
UNIT_TEST_6_PASSED = 0

def ut61_domain_specific_substring_detection():
    UT6_TEST_SUBJECT = 'Unit test6'

    EMAIL_ACCOUNTS = ['insuranservices@autogen.co.za']

    ## UNIT TEST 6 (UT6) - Variant 1 DOMAIN SPECIFIC SUBSTRING DETECTION
    UT61_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'to': 'insuranservices@autogen.co.za',  # This now contains the corrected TO address for bounces
        'from': 'MicrosoftExchange329e71ec88ae4615bbc36ab6ce41109e@telesure.co.za',
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT6_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    #GET THE DETAILS FROM THE EMAIL HEADER
    sender_email = UT61_email_details.get('from')
    recipient_email = UT61_email_details.get('to')


    # CLEAN THE SENDER AND RECIPIENT EMAILS
    sender_clean = sender_email.lower().strip()
    recipient_clean = recipient_email.lower().strip()

    # Check if sender_clean contains both "microsoftexchange" and "telesure.co.za"
    if "microsoftexchange" in sender_clean and "telesure.co.za" in sender_clean:
        reason = "Sender is Microsoft Exchange system at telesure.co.za"
        return True, reason
   

ut61_outcome, ut61_reason = ut61_domain_specific_substring_detection()

if ut61_outcome==True:
    UNIT_TEST_6_PASSED += 1

    print(f"UT 61 - DOMAIN SPECIFIC SUBSTRING DETECTION TEST PASSED: {ut61_reason}")
else:
    print(f"UT 61 - DOMAIN SPECIFIC SUBSTRING DETECTION TEST FAILED: Investigate the issue")


print(f"Unit tests for UT6 completed, Total UT6 tests: {UNIT_TEST_6_COUNT}, Passed: {UNIT_TEST_6_PASSED}, Failed: {UNIT_TEST_6_COUNT - UNIT_TEST_6_PASSED}")


##########################################################################################################################################################

#UNIT TEST SUITE 7 - CHECKING FOR DOMAIN SPECIFIC SUBSTRINGS IN SENDER EMAIL ADDRESS
UNIT_TEST_7_COUNT = 4
UNIT_TEST_7_PASSED = 0

def ut71_domain_specific_substring_detection():
    UT7_TEST_SUBJECT = 'Unit test7'

    EMAIL_ACCOUNTS = ['insuranservices@autogen.co.za']

    ## UNIT TEST 7 (UT7) - Variant 1 DOMAIN SPECIFIC SUBSTRING DETECTION
    UT71_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'to': 'insuranservices@autogen.co.za',  # This now contains the corrected TO address for bounces
        'from': 'noreply@domain.co.za',
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT7_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    #GET THE DETAILS FROM THE EMAIL HEADER
    sender_email = UT71_email_details.get('from')
    recipient_email = UT71_email_details.get('to')


    # CLEAN THE SENDER AND RECIPIENT EMAILS
    sender_clean = sender_email.lower().strip()
    recipient_clean = recipient_email.lower().strip()

    system_indicators = [
        'noreply', 'no-reply', 'donotreply', 'do-not-reply',
        'mailer-daemon', 'postmaster', 'daemon', 'mail-daemon',
        'microsoftexchange', 'exchange', 'outlook-com', 
        'auto-reply', 'autoreply', 'bounce', 'delivery',
        'system', 'noresponse', 'no-response'
    ]
   
    # Check if sender contains any system indicators
    for indicator in system_indicators:
        if indicator in sender_clean:
            reason = f"System/automated sender detected: {sender_email} (contains '{indicator}')"
            return True, reason
    

ut71_outcome, ut71_reason = ut71_domain_specific_substring_detection()

if ut71_outcome==True:
    UNIT_TEST_7_PASSED += 1

    print(f"UT 71 - DOMAIN SPECIFIC SUBSTRING DETECTION TEST PASSED: {ut71_reason}")
else:
    print(f"UT 71 - DOMAIN SPECIFIC SUBSTRING DETECTION TEST FAILED: Investigate the issue")


def ut72_domain_specific_substring_detection():
    UT7_TEST_SUBJECT = 'Unit test7'

    EMAIL_ACCOUNTS = ['insuranservices@autogen.co.za']

    ## UNIT TEST 7 (UT7) - Variant 1 DOMAIN SPECIFIC SUBSTRING DETECTION
    UT72_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'to': 'insuranservices@autogen.co.za',  # This now contains the corrected TO address for bounces
        'from': 'exchange@domain.co.za',
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT7_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    #GET THE DETAILS FROM THE EMAIL HEADER
    sender_email = UT72_email_details.get('from')
    recipient_email = UT72_email_details.get('to')


    # CLEAN THE SENDER AND RECIPIENT EMAILS
    sender_clean = sender_email.lower().strip()
    recipient_clean = recipient_email.lower().strip()

    system_indicators = [
        'noreply', 'no-reply', 'donotreply', 'do-not-reply',
        'mailer-daemon', 'postmaster', 'daemon', 'mail-daemon',
        'microsoftexchange', 'exchange', 'outlook-com', 
        'auto-reply', 'autoreply', 'bounce', 'delivery',
        'system', 'noresponse', 'no-response'
    ]
   
    # Check if sender contains any system indicators
    for indicator in system_indicators:
        if indicator in sender_clean:
            reason = f"System/automated sender detected: {sender_email} (contains '{indicator}')"
            return True, reason
    

ut72_outcome, ut72_reason = ut72_domain_specific_substring_detection()

if ut72_outcome==True:
    UNIT_TEST_7_PASSED += 1

    print(f"UT 72 - DOMAIN SPECIFIC SUBSTRING DETECTION TEST PASSED: {ut72_reason}")
else:
    print(f"UT 72 - DOMAIN SPECIFIC SUBSTRING DETECTION TEST FAILED: Investigate the issue")


def ut73_domain_specific_substring_detection():
    UT7_TEST_SUBJECT = 'Unit test7'

    EMAIL_ACCOUNTS = ['insuranservices@autogen.co.za']

    ## UNIT TEST 7 (UT7) - Variant 1 DOMAIN SPECIFIC SUBSTRING DETECTION
    UT73_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'to': 'insuranservices@autogen.co.za',  # This now contains the corrected TO address for bounces
        'from': 'systemsadmin@domain.co.za',
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT7_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    #GET THE DETAILS FROM THE EMAIL HEADER
    sender_email = UT73_email_details.get('from')
    recipient_email = UT73_email_details.get('to')


    # CLEAN THE SENDER AND RECIPIENT EMAILS
    sender_clean = sender_email.lower().strip()
    recipient_clean = recipient_email.lower().strip()

    system_indicators = [
        'noreply', 'no-reply', 'donotreply', 'do-not-reply',
        'mailer-daemon', 'postmaster', 'daemon', 'mail-daemon',
        'microsoftexchange', 'exchange', 'outlook-com', 
        'auto-reply', 'autoreply', 'bounce', 'delivery',
        'system', 'noresponse', 'no-response'
    ]
   
    # Check if sender contains any system indicators
    for indicator in system_indicators:
        if indicator in sender_clean:
            reason = f"System/automated sender detected: {sender_email} (contains '{indicator}')"
            return True, reason
    

ut73_outcome, ut73_reason = ut73_domain_specific_substring_detection()

if ut73_outcome==True:
    UNIT_TEST_7_PASSED += 1

    print(f"UT 73 - DOMAIN SPECIFIC SUBSTRING DETECTION TEST PASSED: {ut73_reason}")
else:
    print(f"UT 73 - DOMAIN SPECIFIC SUBSTRING DETECTION TEST FAILED: Investigate the issue")


def ut74_domain_specific_substring_detection():
    UT7_TEST_SUBJECT = 'Unit test7'

    EMAIL_ACCOUNTS = ['insuranservices@autogen.co.za']

    ## UNIT TEST 7 (UT7) - Variant 1 DOMAIN SPECIFIC SUBSTRING DETECTION
    UT74_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'to': 'insuranservices@autogen.co.za',  # This now contains the corrected TO address for bounces
        'from': 'noresponse@domain.co.za',
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT7_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    #GET THE DETAILS FROM THE EMAIL HEADER
    sender_email = UT74_email_details.get('from')
    recipient_email = UT74_email_details.get('to')


    # CLEAN THE SENDER AND RECIPIENT EMAILS
    sender_clean = sender_email.lower().strip()
    recipient_clean = recipient_email.lower().strip()

    system_indicators = [
        'noreply', 'no-reply', 'donotreply', 'do-not-reply',
        'mailer-daemon', 'postmaster', 'daemon', 'mail-daemon',
        'microsoftexchange', 'exchange', 'outlook-com', 
        'auto-reply', 'autoreply', 'bounce', 'delivery',
        'system', 'noresponse', 'no-response'
    ]
   
    # Check if sender contains any system indicators
    for indicator in system_indicators:
        if indicator in sender_clean:
            reason = f"System/automated sender detected: {sender_email} (contains '{indicator}')"
            return True, reason
    

ut74_outcome, ut74_reason = ut74_domain_specific_substring_detection()

if ut74_outcome==True:
    UNIT_TEST_7_PASSED += 1

    print(f"UT 74 - DOMAIN SPECIFIC SUBSTRING DETECTION TEST PASSED: {ut74_reason}")
else:
    print(f"UT 74 - DOMAIN SPECIFIC SUBSTRING DETECTION TEST FAILED: Investigate the issue")

print(f"Unit tests for UT7 completed, Total UT7 tests: {UNIT_TEST_7_COUNT}, Passed: {UNIT_TEST_7_PASSED}, Failed: {UNIT_TEST_7_COUNT - UNIT_TEST_7_PASSED}")


##########################################################################################################################################################

#UNIT TEST SUITE 7 - CHECKING FOR DOMAIN SPECIFIC SUBSTRINGS IN SENDER EMAIL ADDRESS
UNIT_TEST_7_COUNT = 4
UNIT_TEST_7_PASSED = 0

def ut71_domain_specific_substring_detection():
    UT7_TEST_SUBJECT = 'Unit test7'

    EMAIL_ACCOUNTS = ['insuranservices@autogen.co.za']

    ## UNIT TEST 7 (UT7) - Variant 1 DOMAIN SPECIFIC SUBSTRING DETECTION
    UT71_email_details = {
        'email_id': 'ABC123',
        'internet_message_id': 'XYZ123',
        'to': 'insuranservices@autogen.co.za',  # This now contains the corrected TO address for bounces
        'from': 'noreply@domain.co.za',
        'date_received': '2025-06-17 08:18:36.000',
        'cc': '',
        'subject': UT7_TEST_SUBJECT,
        'body_html': 'body text html',
        'body_text': 'body text',
        'is_bounce_message': False  # Add flag to indicate if this is a bounce
    }

    #GET THE DETAILS FROM THE EMAIL HEADER
    sender_email = UT71_email_details.get('from')
    recipient_email = UT71_email_details.get('to')


    # CLEAN THE SENDER AND RECIPIENT EMAILS
    sender_clean = sender_email.lower().strip()
    recipient_clean = recipient_email.lower().strip()

    system_indicators = [
        'noreply', 'no-reply', 'donotreply', 'do-not-reply',
        'mailer-daemon', 'postmaster', 'daemon', 'mail-daemon',
        'microsoftexchange', 'exchange', 'outlook-com', 
        'auto-reply', 'autoreply', 'bounce', 'delivery',
        'system', 'noresponse', 'no-response'
    ]
   
    # Check if sender contains any system indicators
    for indicator in system_indicators:
        if indicator in sender_clean:
            reason = f"System/automated sender detected: {sender_email} (contains '{indicator}')"
            return True, reason
    

ut71_outcome, ut71_reason = ut71_domain_specific_substring_detection()

if ut71_outcome==True:
    UNIT_TEST_7_PASSED += 1

    print(f"UT 71 - DOMAIN SPECIFIC SUBSTRING DETECTION TEST PASSED: {ut71_reason}")
else:
    print(f"UT 71 - DOMAIN SPECIFIC SUBSTRING DETECTION TEST FAILED: Investigate the issue")


