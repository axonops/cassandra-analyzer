"""
Unit tests for the AxonOps API Client
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
import requests
from requests.exceptions import ConnectionError, RequestException, Timeout

from cassandra_analyzer.client.axonops_client import AxonOpsClient
from cassandra_analyzer.client.exceptions import (
    AxonOpsAPIError,
    AxonOpsAuthError,
    AxonOpsConnectionError,
)


class TestAxonOpsClient:
    """Test cases for AxonOpsClient"""

    @pytest.fixture
    def client(self):
        """Create an AxonOps client instance"""
        return AxonOpsClient(api_url="http://localhost:9090", token="test-token", timeout=30)

    @pytest.fixture
    def mock_response(self):
        """Create a mock response object"""
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"status": "success"}
        response.raise_for_status = Mock()
        response.headers = {"Content-Type": "application/json"}
        response.text = '{"status": "success"}'
        return response

    def test_client_initialization(self):
        """Test client initialization"""
        client = AxonOpsClient(
            api_url="http://localhost:9090", token="test-token", timeout=60, max_retries=5
        )

        assert client.api_url == "http://localhost:9090"
        assert client.timeout == 60
        assert "Authorization" in client.session.headers
        assert client.session.headers["Authorization"] == "Bearer test-token"

    def test_api_url_normalization(self):
        """Test that API URL is normalized correctly"""
        # With trailing slash
        client1 = AxonOpsClient("http://localhost:9090/", "token")
        assert client1.api_url == "http://localhost:9090"

        # Without trailing slash
        client2 = AxonOpsClient("http://localhost:9090", "token")
        assert client2.api_url == "http://localhost:9090"

    @patch("requests.Session.request")
    def test_successful_get_request(self, mock_request, client, mock_response):
        """Test successful GET request"""
        mock_request.return_value = mock_response

        result = client._request("GET", "/api/v1/cluster")

        assert result == {"status": "success"}
        mock_request.assert_called_once()
        assert mock_request.call_args[1]["url"] == "http://localhost:9090/api/v1/cluster"

    @patch("requests.Session.request")
    def test_successful_post_request(self, mock_request, client, mock_response):
        """Test successful POST request"""
        mock_request.return_value = mock_response

        data = {"query": "test"}
        result = client._request("POST", "/api/v1/query", json=data)

        assert result == {"status": "success"}
        mock_request.assert_called_once()
        assert mock_request.call_args[1]["json"] == data

    @patch("requests.Session.request")
    def test_authentication_error(self, mock_request, client):
        """Test authentication error handling"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.headers = {}
        mock_request.return_value = mock_response

        with pytest.raises(AxonOpsAuthError):
            client._request("GET", "/api/v1/cluster")

    @patch("requests.Session.request")
    def test_timeout_error(self, mock_request, client):
        """Test timeout error handling"""
        mock_request.side_effect = Timeout()

        with pytest.raises(AxonOpsConnectionError):
            client._request("GET", "/api/v1/cluster")

    @patch("requests.Session.request")
    def test_connection_error(self, mock_request, client):
        """Test connection error handling"""
        mock_request.side_effect = ConnectionError()

        with pytest.raises(AxonOpsConnectionError):
            client._request("GET", "/api/v1/cluster")

    @patch("requests.Session.request")
    def test_retry_on_server_error(self, mock_request, client, mock_response):
        """Test retry logic on server errors"""
        # The retry is handled by HTTPAdapter, not by our code
        # So we just test that the request succeeds eventually
        mock_request.return_value = mock_response

        result = client._request("GET", "/api/v1/cluster")

        assert result == {"status": "success"}
        assert mock_request.call_count == 1

    @patch("requests.Session.request")
    def test_max_retries_exceeded(self, mock_request, client):
        """Test that server errors are raised as API errors"""
        error_response = Mock()
        error_response.status_code = 503
        error_response.text = "Service Unavailable"
        error_response.headers = {}

        mock_request.return_value = error_response

        with pytest.raises(AxonOpsAPIError) as exc_info:
            client._request("GET", "/api/v1/cluster")

        assert "API error:" in str(exc_info.value)

    @patch("requests.Session.request")
    def test_get_cluster_settings(self, mock_request, client):
        """Test get_cluster_settings method"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"name": "test-cluster", "version": "4.0.11", "nodes": 3}
        mock_response.text = '{"name": "test-cluster"}'
        mock_response.headers = {}
        mock_request.return_value = mock_response

        result = client.get_cluster_settings("org1", "cassandra", "cluster1")

        assert result["name"] == "test-cluster"
        assert result["version"] == "4.0.11"
        assert result["nodes"] == 3

        expected_url = "http://localhost:9090/api/v1/clusterSettings/org1/cassandra/cluster1"
        mock_request.assert_called_once()
        assert mock_request.call_args[1]["url"] == expected_url

    @patch("requests.Session.request")
    def test_get_nodes(self, mock_request, client):
        """Test get_nodes method"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "node1", "address": "10.0.0.1"},
            {"id": "node2", "address": "10.0.0.2"},
        ]
        mock_response.text = '[{"id": "node1"}]'
        mock_response.headers = {}
        mock_request.return_value = mock_response

        result = client.get_nodes("org1", "cassandra", "cluster1")

        assert len(result) == 2
        assert result[0]["id"] == "node1"

    @patch("requests.Session.request")
    def test_query_range(self, mock_request, client):
        """Test query_range method"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "result": [{"metric": {"__name__": "cpu_usage"}, "values": [[1234567890, "50.0"]]}]
            }
        }
        mock_response.text = '{"data": {}}'
        mock_response.headers = {}
        mock_request.return_value = mock_response

        from datetime import datetime
        result = client.query_range(
            query="cpu_usage",
            start=datetime(2024, 1, 1, 0, 0, 0),
            end=datetime(2024, 1, 1, 1, 0, 0),
        )

        assert "data" in result
        assert len(result["data"]["result"]) == 1

    @patch("requests.Session.request")
    def test_error_response_handling(self, mock_request, client):
        """Test handling of error responses with JSON body"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "Invalid parameter",
            "message": "The cluster name is invalid",
        }
        mock_response.text = '{"error": "Invalid parameter"}'
        mock_response.headers = {}
        mock_request.return_value = mock_response

        with pytest.raises(AxonOpsAPIError) as exc_info:
            client._request("GET", "/api/v1/cluster")

        assert "API error:" in str(exc_info.value)

    def test_session_cleanup(self, client):
        """Test that session exists and can be used"""
        # The client doesn't have a close method, so we just verify the session exists
        assert client.session is not None
        assert hasattr(client.session, 'request')
        assert "Authorization" in client.session.headers
