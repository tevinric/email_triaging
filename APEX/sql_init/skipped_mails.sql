-- Create the skipped_mails table

USE APEXDEV;

CREATE TABLE [dbo].[skipped_mails] (
    -- Core identification fields
    [id] varchar(50) NOT NULL,                    -- Unique identifier for each skipped email entry (UUID)
    [eml_id] varchar(MAX) NULL,                   -- Email ID from the original email
    [internet_message_id] varchar(900) NULL,     -- Internet message ID for linking (limited for indexing)
    
    -- Email timing information
    [dttm_rec] datetime NULL,                     -- Date/time when email was received
    [dttm_proc] datetime NULL,                    -- Date/time when email was processed (skipped)
    
    -- Email header information
    [eml_frm] varchar(MAX) NULL,                  -- Email sender (FROM field)
    [eml_to] varchar(MAX) NULL,                   -- Email recipient (TO field)
    [eml_cc] varchar(MAX) NULL,                   -- Email CC recipients
    [eml_subject] varchar(MAX) NULL,              -- Email subject line
    [eml_body] varchar(MAX) NULL,                 -- Email body content (truncated if too long)
    
    -- Skip reason and metadata
    [rsn_skipped] varchar(MAX) NOT NULL,          -- Reason why the email was skipped
    [created_timestamp] datetime NOT NULL DEFAULT GETDATE(), -- When this skip record was created
    
    -- Additional tracking fields
    [processing_time_seconds] float NULL DEFAULT 0.0, -- Time spent before skipping
    [account_processed] varchar(500) NULL,        -- Which email account was being processed
    [skip_type] varchar(100) NULL DEFAULT 'DUPLICATE' -- Type of skip (DUPLICATE, ERROR, etc.)
);

-- Add primary key constraint
ALTER TABLE [dbo].[skipped_mails] ADD CONSTRAINT [PK_skipped_mails] PRIMARY KEY ([id]);

-- Add indexes for better performance on commonly queried fields
CREATE INDEX [IX_skipped_mails_internet_message_id] ON [dbo].[skipped_mails] ([internet_message_id]);
CREATE INDEX [IX_skipped_mails_created_timestamp] ON [dbo].[skipped_mails] ([created_timestamp]);
CREATE INDEX [IX_skipped_mails_dttm_proc] ON [dbo].[skipped_mails] ([dttm_proc]);
CREATE INDEX [IX_skipped_mails_skip_type] ON [dbo].[skipped_mails] ([skip_type]);
CREATE INDEX [IX_skipped_mails_rsn_skipped] ON [dbo].[skipped_mails] ([rsn_skipped]);

-- Composite index for common queries
