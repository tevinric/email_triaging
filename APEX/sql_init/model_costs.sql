CREATE TABLE model_costs (
    model NVARCHAR(255) NOT NULL,
    prompt_cost DECIMAL(18, 4) NOT NULL,
    completion_cost DECIMAL(18, 4) NOT NULL,
    cache_cost DECIMAL(18, 4) NOT NULL,
    PRIMARY KEY (model)  -- Assuming model is unique, you can modify this as needed
);

-- Add records:
INSERT INTO [APEXSIT].[dbo].[model_costs] (model, prompt_cost, completion_cost, cache_cost)
VALUES 
('gpt-4o', 2.5,10.0, 1.25),
('gpt-4o-mini', 0.15, 0.6, 0.075),