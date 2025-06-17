-- SQL script to create the system_logs table
-- This table will store terminal log outputs for each email processed

-- Create the system_logs table
CREATE TABLE [dbo].[system_logs] (
    [id] varchar(50) NOT NULL,                    -- Unique identifier for each log entry (UUID)
    [eml_id] varchar(MAX) NULL,                   -- Email ID from the main logs table
    [internet_message_id] varchar(900) NULL,     -- Internet message ID for linking with main logs (limited for indexing)
    [log_details] text NOT NULL,                 -- The complete log text for this email's processing
    [log_entry_count] int NULL,                  -- Number of individual log entries captured
    [created_timestamp] datetime NOT NULL,       -- When this system log was created
    [processing_start_time] datetime NULL,       -- When email processing started
    [processing_end_time] datetime NULL,         -- When email processing ended
    [email_subject] varchar(500) NULL            -- Email subject for easier identification
);

-- Add indexes for better performance
CREATE INDEX [IX_system_logs_id] ON [dbo].[system_logs] ([id]);
CREATE INDEX [IX_system_logs_internet_message_id] ON [dbo].[system_logs] ([internet_message_id]);
CREATE INDEX [IX_system_logs_eml_id] ON [dbo].[system_logs] ([eml_id]);
CREATE INDEX [IX_system_logs_created_timestamp] ON [dbo].[system_logs] ([created_timestamp]);

-- Grant permissions if needed (adjust user/role as per your setup)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON [dbo].[system_logs] TO [your_user_or_role];

PRINT 'system_logs table created successfully with indexes.';
