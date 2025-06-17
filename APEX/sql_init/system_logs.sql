-- Enhanced SQL script to create the system_logs table with comprehensive autoresponse tracking
-- This table will store terminal log outputs and detailed autoresponse information for each email processed

-- Drop the existing table if it exists (use with caution in production)
IF OBJECT_ID('[dbo].[system_logs]', 'U') IS NOT NULL
BEGIN
    DROP TABLE [dbo].[system_logs];
    PRINT 'Existing system_logs table dropped.';
END

-- Create the enhanced system_logs table with comprehensive autoresponse and error tracking
CREATE TABLE [dbo].[system_logs] (
    -- Core identification fields
    [id] varchar(50) NOT NULL,                    -- Unique identifier for each log entry (UUID)
    [eml_id] varchar(MAX) NULL,                   -- Email ID from the main logs table
    [internet_message_id] varchar(900) NULL,     -- Internet message ID for linking with main logs (limited for indexing)
    
    -- Log content and metadata
    [log_details] text NOT NULL,                 -- The complete log text for this email's processing (now JSON format)
    [log_entry_count] int NULL,                  -- Number of individual log entries captured
    [created_timestamp] datetime NOT NULL,       -- When this system log was created
    [processing_start_time] datetime NULL,       -- When email processing started
    [processing_end_time] datetime NULL,         -- When email processing ended
    [processing_duration_seconds] float NULL,    -- Total processing time in seconds
    [email_subject] varchar(500) NULL,           -- Email subject for easier identification
    
    -- Error and warning tracking
    [total_errors] int NULL DEFAULT 0,           -- Total number of errors encountered during processing
    [total_warnings] int NULL DEFAULT 0,         -- Total number of warnings encountered during processing
    
    -- Enhanced autoresponse tracking fields
    [autoresponse_attempted] bit NULL DEFAULT 0, -- Whether autoresponse was attempted (True/False)
    [autoresponse_successful] bit NULL DEFAULT 0, -- Whether autoresponse was sent successfully (True/False)
    [autoresponse_skip_reason] varchar(MAX) NULL, -- Reason why autoresponse was skipped (if applicable)
    [template_folder_used] varchar(200) NULL,    -- Template folder name used for autoresponse
    [autoresponse_subject] varchar(500) NULL,    -- Subject line used in the autoresponse
    [autoresponse_recipient] varchar(500) NULL,  -- Email address that received the autoresponse
    [autoresponse_error] varchar(MAX) NULL,      -- Error message if autoresponse failed
    
    -- Log statistics for quick analysis
    [log_stats_json] varchar(MAX) NULL           -- JSON string containing detailed log statistics
);

-- Add indexes for better performance on commonly queried fields
CREATE INDEX [IX_system_logs_id] ON [dbo].[system_logs] ([id]);
CREATE INDEX [IX_system_logs_internet_message_id] ON [dbo].[system_logs] ([internet_message_id]);
CREATE INDEX [IX_system_logs_eml_id] ON [dbo].[system_logs] ([eml_id]);
CREATE INDEX [IX_system_logs_created_timestamp] ON [dbo].[system_logs] ([created_timestamp]);
CREATE INDEX [IX_system_logs_processing_start_time] ON [dbo].[system_logs] ([processing_start_time]);

-- Additional indexes for autoresponse analysis
CREATE INDEX [IX_system_logs_autoresponse_attempted] ON [dbo].[system_logs] ([autoresponse_attempted]);
CREATE INDEX [IX_system_logs_autoresponse_successful] ON [dbo].[system_logs] ([autoresponse_successful]);
CREATE INDEX [IX_system_logs_template_folder] ON [dbo].[system_logs] ([template_folder_used]);

-- Composite index for common queries
CREATE INDEX [IX_system_logs_timestamp_autoresponse] ON [dbo].[system_logs] ([created_timestamp], [autoresponse_attempted], [autoresponse_successful]);

-- Grant permissions if needed (adjust user/role as per your setup)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON [dbo].[system_logs] TO [your_user_or_role];

PRINT 'Enhanced system_logs table created successfully with comprehensive autoresponse tracking and indexes.';

-- Sample queries for monitoring autoresponse performance
PRINT 'Sample monitoring queries:';
PRINT '-- Autoresponse success rate:';
PRINT 'SELECT ';
PRINT '    COUNT(*) as total_emails,';
PRINT '    SUM(CASE WHEN autoresponse_attempted = 1 THEN 1 ELSE 0 END) as autoresponse_attempts,';
PRINT '    SUM(CASE WHEN autoresponse_successful = 1 THEN 1 ELSE 0 END) as autoresponse_successes,';
PRINT '    CASE WHEN SUM(CASE WHEN autoresponse_attempted = 1 THEN 1 ELSE 0 END) > 0';
PRINT '         THEN CAST(SUM(CASE WHEN autoresponse_successful = 1 THEN 1 ELSE 0 END) * 100.0 / SUM(CASE WHEN autoresponse_attempted = 1 THEN 1 ELSE 0 END) AS DECIMAL(5,2))';
PRINT '         ELSE 0 END as success_rate_percentage';
PRINT 'FROM [dbo].[system_logs]';
PRINT 'WHERE created_timestamp >= DATEADD(DAY, -7, GETDATE());';
PRINT '';
PRINT '-- Top autoresponse skip reasons:';
PRINT 'SELECT ';
PRINT '    autoresponse_skip_reason,';
PRINT '    COUNT(*) as frequency';
PRINT 'FROM [dbo].[system_logs]';
PRINT 'WHERE autoresponse_attempted = 1 AND autoresponse_successful = 0';
PRINT '    AND autoresponse_skip_reason IS NOT NULL';
PRINT '    AND created_timestamp >= DATEADD(DAY, -7, GETDATE())';
PRINT 'GROUP BY autoresponse_skip_reason';
PRINT 'ORDER BY frequency DESC;';
PRINT '';
PRINT '-- Template usage statistics:';
PRINT 'SELECT ';
PRINT '    template_folder_used,';
PRINT '    COUNT(*) as usage_count,';
PRINT '    SUM(CASE WHEN autoresponse_successful = 1 THEN 1 ELSE 0 END) as successful_sends';
PRINT 'FROM [dbo].[system_logs]';
PRINT 'WHERE autoresponse_attempted = 1';
PRINT '    AND template_folder_used IS NOT NULL';
PRINT '    AND created_timestamp >= DATEADD(DAY, -7, GETDATE())';
PRINT 'GROUP BY template_folder_used';
PRINT 'ORDER BY usage_count DESC;';
