import pytest
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types import CompletionUsage

# Import the module to test
from apex_llm.apex import apex_categorise, apex_action_check, apex_prioritize

# Import sample data for tests
from tests.mock_data.email_samples import (
    AMENDMENTS_EMAIL,
    ASSIST_EMAIL,
    VEHICLE_TRACKING_EMAIL,
    BAD_SERVICE_EMAIL,
    CLAIMS_EMAIL,
    REFUND_REQUEST_EMAIL,
    DOCUMENT_REQUEST_EMAIL,
    ONLINE_APP_EMAIL,
    RETENTIONS_EMAIL,
    REQUEST_QUOTE_EMAIL,
    DEBIT_ORDER_EMAIL,
    PREVIOUS_INSURANCE_EMAIL,
    OTHER_EMAIL
)

# Helper function to create a mock OpenAI response
def create_mock_response(content, completion_tokens=100, prompt_tokens=200):
    """Create a mock OpenAI API response with the specified content."""
    mock_message = ChatCompletionMessage(role="assistant", content=content, function_call=None, tool_calls=None)
    mock_usage = CompletionUsage(completion_tokens=completion_tokens, prompt_tokens=prompt_tokens, total_tokens=completion_tokens + prompt_tokens)
    
    mock_completion = MagicMock(spec=ChatCompletion)
    mock_completion.choices = [MagicMock(message=mock_message)]
    mock_completion.usage = mock_usage
    
    return mock_completion

# Mock responses for different email categories
@pytest.fixture
def mock_amendments_response():
    content = json.dumps({
        "classification": ["amendments", "vehicle tracking", "other"],
        "rsn_classification": "Email requests changes to policy details.",
        "action_required": "yes",
        "sentiment": "neutral"
    })
    return create_mock_response(content)

@pytest.fixture
def mock_assist_response():
    content = json.dumps({
        "classification": ["assist", "other", "amendments"],
        "rsn_classification": "Customer is requesting roadside assistance.",
        "action_required": "yes",
        "sentiment": "neutral"
    })
    return create_mock_response(content)

@pytest.fixture
def mock_vehicle_tracking_response():
    content = json.dumps({
        "classification": ["vehicle tracking", "amendments", "online/app"],
        "rsn_classification": "Email contains vehicle tracking device certificate.",
        "action_required": "yes",
        "sentiment": "neutral"
    })
    return create_mock_response(content)

@pytest.fixture
def mock_bad_service_response():
    content = json.dumps({
        "classification": ["bad service/experience", "claims", "other"],
        "rsn_classification": "Customer is complaining about poor service.",
        "action_required": "yes",
        "sentiment": "negative"
    })
    return create_mock_response(content)

@pytest.fixture
def mock_claims_response():
    content = json.dumps({
        "classification": ["claims", "document request", "amendments"],
        "rsn_classification": "Customer is filing an insurance claim.",
        "action_required": "yes",
        "sentiment": "neutral"
    })
    return create_mock_response(content)

@pytest.fixture
def mock_refund_request_response():
    content = json.dumps({
        "classification": ["refund request", "amendments", "bad service/experience"],
        "rsn_classification": "Customer is requesting a refund.",
        "action_required": "yes",
        "sentiment": "neutral"
    })
    return create_mock_response(content)

@pytest.fixture
def mock_document_request_response():
    content = json.dumps({
        "classification": ["document request", "other", "amendments"],
        "rsn_classification": "Customer is requesting policy documents.",
        "action_required": "yes",
        "sentiment": "neutral"
    })
    return create_mock_response(content)

@pytest.fixture
def mock_online_app_response():
    content = json.dumps({
        "classification": ["online/app", "document request", "other"],
        "rsn_classification": "Customer is reporting an issue with the online system.",
        "action_required": "yes",
        "sentiment": "negative"
    })
    return create_mock_response(content)

@pytest.fixture
def mock_retentions_response():
    content = json.dumps({
        "classification": ["retentions", "amendments", "other"],
        "rsn_classification": "Customer wants to cancel their policy.",
        "action_required": "yes",
        "sentiment": "neutral"
    })
    return create_mock_response(content)

@pytest.fixture
def mock_request_quote_response():
    content = json.dumps({
        "classification": ["request for quote", "amendments", "other"],
        "rsn_classification": "Customer is requesting an insurance quote.",
        "action_required": "yes",
        "sentiment": "neutral"
    })
    return create_mock_response(content)

@pytest.fixture
def mock_debit_order_response():
    content = json.dumps({
        "classification": ["debit order switch", "amendments", "other"],
        "rsn_classification": "Bank is requesting a change to customer's debit order details.",
        "action_required": "yes",
        "sentiment": "neutral"
    })
    return create_mock_response(content)

@pytest.fixture
def mock_previous_insurance_response():
    content = json.dumps({
        "classification": ["previous insurance checks/queries", "request for quote", "other"],
        "rsn_classification": "Request for previous insurance verification.",
        "action_required": "yes",
        "sentiment": "neutral"
    })
    return create_mock_response(content)

@pytest.fixture
def mock_other_response():
    content = json.dumps({
        "classification": ["other", "amendments", "document request"],
        "rsn_classification": "Email doesn't fit into any specific category.",
        "action_required": "no",
        "sentiment": "neutral"
    })
    return create_mock_response(content)

@pytest.fixture
def mock_error_response():
    # Mock a failed API response
    mock = MagicMock()
    mock.choices = []
    mock.usage = None
    return mock

@pytest.fixture
def mock_action_check_response_yes():
    content = json.dumps({
        "action_required": "yes"
    })
    return create_mock_response(content, completion_tokens=20, prompt_tokens=50)

@pytest.fixture
def mock_action_check_response_no():
    content = json.dumps({
        "action_required": "no"
    })
    return create_mock_response(content, completion_tokens=20, prompt_tokens=50)

@pytest.fixture
def mock_prioritize_response():
    content = json.dumps({
        "final_category": "amendments",
        "rsn_classification": "Based on the context, this is a policy amendment request."
    })
    return create_mock_response(content, completion_tokens=20, prompt_tokens=50)


# Test cases for apex_categorise function
@pytest.mark.asyncio
async def test_apex_categorise_amendments(mock_amendments_response):
    """Test classification of an amendments email."""
    with patch('apex_llm.apex.client.chat.completions.create', return_value=mock_amendments_response):
        with patch('apex_llm.apex.apex_action_check', new_callable=AsyncMock) as mock_action_check:
            mock_action_check.return_value = {
                "response": "200", 
                "message": {"action_required": "yes", "apex_cost_usd": 0.00002}
            }
            with patch('apex_llm.apex.apex_prioritize', new_callable=AsyncMock) as mock_prioritize:
                mock_prioritize.return_value = {
                    "response": "200", 
                    "message": {
                        "final_category": "amendments", 
                        "rsn_classification": "Email requests changes to policy details.", 
                        "apex_cost_usd": 0.00001
                    }
                }
                
                result = await apex_categorise(AMENDMENTS_EMAIL)
                
                # Verify result structure
                assert result["response"] == "200"
                assert "message" in result
                
                # Verify message content
                message = result["message"]
                assert message["classification"] == "amendments"
                assert "rsn_classification" in message
                assert message["action_required"] == "yes"
                assert message["sentiment"] == "neutral"
                assert "apex_cost_usd" in message

@pytest.mark.asyncio
async def test_apex_categorise_assist(mock_assist_response):
    """Test classification of an assist email."""
    with patch('apex_llm.apex.client.chat.completions.create', return_value=mock_assist_response):
        with patch('apex_llm.apex.apex_action_check', new_callable=AsyncMock) as mock_action_check:
            mock_action_check.return_value = {
                "response": "200", 
                "message": {"action_required": "yes", "apex_cost_usd": 0.00002}
            }
            with patch('apex_llm.apex.apex_prioritize', new_callable=AsyncMock) as mock_prioritize:
                mock_prioritize.return_value = {
                    "response": "200", 
                    "message": {
                        "final_category": "assist", 
                        "rsn_classification": "Customer is requesting roadside assistance.", 
                        "apex_cost_usd": 0.00001
                    }
                }
                
                result = await apex_categorise(ASSIST_EMAIL)
                
                # Verify message content
                message = result["message"]
                assert message["classification"] == "assist"
                assert message["action_required"] == "yes"

@pytest.mark.asyncio
async def test_apex_categorise_vehicle_tracking(mock_vehicle_tracking_response):
    """Test classification of a vehicle tracking email."""
    with patch('apex_llm.apex.client.chat.completions.create', return_value=mock_vehicle_tracking_response):
        with patch('apex_llm.apex.apex_action_check', new_callable=AsyncMock) as mock_action_check:
            mock_action_check.return_value = {
                "response": "200", 
                "message": {"action_required": "yes", "apex_cost_usd": 0.00002}
            }
            with patch('apex_llm.apex.apex_prioritize', new_callable=AsyncMock) as mock_prioritize:
                mock_prioritize.return_value = {
                    "response": "200", 
                    "message": {
                        "final_category": "vehicle tracking", 
                        "rsn_classification": "Email contains vehicle tracking device certificate.", 
                        "apex_cost_usd": 0.00001
                    }
                }
                
                result = await apex_categorise(VEHICLE_TRACKING_EMAIL)
                
                # Verify message content
                message = result["message"]
                assert message["classification"] == "vehicle tracking"
                assert message["action_required"] == "yes"

@pytest.mark.asyncio
async def test_apex_categorise_bad_service(mock_bad_service_response):
    """Test classification of a bad service/experience email."""
    with patch('apex_llm.apex.client.chat.completions.create', return_value=mock_bad_service_response):
        with patch('apex_llm.apex.apex_action_check', new_callable=AsyncMock) as mock_action_check:
            mock_action_check.return_value = {
                "response": "200", 
                "message": {"action_required": "yes", "apex_cost_usd": 0.00002}
            }
            with patch('apex_llm.apex.apex_prioritize', new_callable=AsyncMock) as mock_prioritize:
                mock_prioritize.return_value = {
                    "response": "200", 
                    "message": {
                        "final_category": "bad service/experience", 
                        "rsn_classification": "Customer is complaining about poor service.", 
                        "apex_cost_usd": 0.00001
                    }
                }
                
                result = await apex_categorise(BAD_SERVICE_EMAIL)
                
                # Verify message content
                message = result["message"]
                assert message["classification"] == "bad service/experience"
                assert message["sentiment"] == "negative"

@pytest.mark.asyncio
async def test_apex_categorise_claims(mock_claims_response):
    """Test classification of a claims email."""
    with patch('apex_llm.apex.client.chat.completions.create', return_value=mock_claims_response):
        with patch('apex_llm.apex.apex_action_check', new_callable=AsyncMock) as mock_action_check:
            mock_action_check.return_value = {
                "response": "200", 
                "message": {"action_required": "yes", "apex_cost_usd": 0.00002}
            }
            with patch('apex_llm.apex.apex_prioritize', new_callable=AsyncMock) as mock_prioritize:
                mock_prioritize.return_value = {
                    "response": "200", 
                    "message": {
                        "final_category": "claims", 
                        "rsn_classification": "Customer is filing an insurance claim.", 
                        "apex_cost_usd": 0.00001
                    }
                }
                
                result = await apex_categorise(CLAIMS_EMAIL)
                
                # Verify message content
                message = result["message"]
                assert message["classification"] == "claims"

# Testing error handling
@pytest.mark.asyncio
async def test_apex_categorise_api_error():
    """Test handling of API errors."""
    with patch('apex_llm.apex.client.chat.completions.create', side_effect=Exception("API Error")):
        result = await apex_categorise("Test email content")
        
        # Verify error handling
        assert result["response"] == "500"
        assert "API Error" in result["message"]

# Test action check function
@pytest.mark.asyncio
async def test_apex_action_check_yes(mock_action_check_response_yes):
    """Test action check function when action is required."""
    with patch('apex_llm.apex.client.chat.completions.create', return_value=mock_action_check_response_yes):
        result = await apex_action_check("Please help me with my policy")
        
        # Verify result
        assert result["response"] == "200"
        assert result["message"]["action_required"] == "yes"
        assert "apex_cost_usd" in result["message"]

@pytest.mark.asyncio
async def test_apex_action_check_no(mock_action_check_response_no):
    """Test action check function when no action is required."""
    with patch('apex_llm.apex.client.chat.completions.create', return_value=mock_action_check_response_no):
        result = await apex_action_check("Just confirming receipt of your email")
        
        # Verify result
        assert result["response"] == "200"
        assert result["message"]["action_required"] == "no"

# Test prioritize function
@pytest.mark.asyncio
async def test_apex_prioritize(mock_prioritize_response):
    """Test category prioritization function."""
    with patch('apex_llm.apex.client.chat.completions.create', return_value=mock_prioritize_response):
        result = await apex_prioritize("Test email content", ["amendments", "document request", "other"])
        
        # Verify result
        assert result["response"] == "200"
        assert result["message"]["final_category"] == "amendments"
        assert "rsn_classification" in result["message"]
        assert "apex_cost_usd" in result["message"]

# Integration test - test the full classification pipeline
@pytest.mark.asyncio
async def test_apex_categorise_with_action_override(mock_claims_response):
    """Test classification with action check override."""
    with patch('apex_llm.apex.client.chat.completions.create', return_value=mock_claims_response):
        with patch('apex_llm.apex.apex_action_check', new_callable=AsyncMock) as mock_action_check:
            # Action check returns opposite of what the main classification returns
            mock_action_check.return_value = {
                "response": "200", 
                "message": {"action_required": "no", "apex_cost_usd": 0.00002}
            }
            with patch('apex_llm.apex.apex_prioritize', new_callable=AsyncMock) as mock_prioritize:
                mock_prioritize.return_value = {
                    "response": "200", 
                    "message": {
                        "final_category": "claims", 
                        "rsn_classification": "Customer is filing an insurance claim.", 
                        "apex_cost_usd": 0.00001
                    }
                }
                
                result = await apex_categorise(CLAIMS_EMAIL)
                
                # Verify the action required was overridden
                assert result["message"]["action_required"] == "no"
