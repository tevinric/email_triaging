IF OBJECT_ID('[dbo].[logs]', 'U') IS NOT NULL
BEGIN
    DROP TABLE [dbo].[logs];
END

-- Create the logs table with all columns
CREATE TABLE [dbo].[logs] (
    [id] varchar(50) NULL,
    [eml_id] varchar(MAX) NULL,
    [internet_message_id] varchar(MAX) NULL,
    [dttm_rec] datetime NULL,
    [dttm_proc] datetime NULL,
    [eml_to] varchar(MAX) NULL,
    [eml_frm] varchar(MAX) NULL,
    [eml_cc] varchar(MAX) NULL,
    [eml_sub] varchar(MAX) NULL,
    [eml_bdy] varchar(MAX) NULL,
    [apex_class] varchar(MAX) NULL,
    [apex_class_rsn] text NULL,
    [apex_action_req] text NULL,
    [apex_sentiment] varchar(50) NULL,
    [apex_cost_usd] float NULL,
    [apex_routed_to] varchar(MAX) NULL,
    [sts_read_eml] text NULL,
    [sts_class] text NULL,
    [sts_routing] text NULL,
    [tat] float NULL,
    [end_time] datetime NULL,
    [apex_intervention] text NULL,
    [apex_top_categories] varchar(MAX) NULL
);

-- Add an index on internet_message_id for faster lookups
CREATE INDEX [IX_logs_internet_message_id] ON [dbo].[logs] ([id]);
CREATE INDEX [IX_logs_eml_id] ON [dbo].[logs] ([internet_message_id]);
