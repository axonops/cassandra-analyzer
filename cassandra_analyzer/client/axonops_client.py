"""
AxonOps API client implementation
"""

import requests
from typing import Dict, List, Any, Optional
from datetime import datetime
import structlog
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from .exceptions import (
    AxonOpsAPIError,
    AxonOpsAuthError,
    AxonOpsConnectionError,
    AxonOpsNotFoundError,
)

logger = structlog.get_logger()


class AxonOpsClient:
    """Client for interacting with AxonOps API"""
    
    def __init__(self, api_url: str, token: str, timeout: int = 30, max_retries: int = 3):
        self.api_url = api_url.rstrip('/')
        self.token = token
        self.timeout = timeout
        self.org = None  # Will be set when making org-specific requests
        
        # Configure session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set authorization header
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "axonops-analyzer/1.0.0",
        })
    
    def _request(self, method: str, endpoint: str, org: str = None, **kwargs) -> Dict[str, Any]:
        """Make an API request"""
        # Fix URL construction: urljoin treats absolute paths as replacements
        # Use simple concatenation with proper slash handling instead
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        
        # Add organization header if provided (helps API route correctly)
        headers = kwargs.get('headers', {})
        if org:
            headers['X-Grafana-Org-Id'] = org
        if headers:
            kwargs['headers'] = headers
        
        # Log the request details
        logger.debug(
            "API Request",
            method=method,
            url=url,
            headers={k: v for k, v in self.session.headers.items() if k != 'Authorization'} | headers,
            params=kwargs.get('params', {}),
            json=kwargs.get('json', {})
        )
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                timeout=self.timeout,
                **kwargs
            )
            
            # Log response details
            logger.debug(
                "API Response",
                status_code=response.status_code,
                headers=dict(response.headers),
                content_length=len(response.text) if response.text else 0,
                # Log first 500 chars of response for debugging
                content_preview=response.text[:500] if response.text else ""
            )
            
            if response.status_code == 401:
                raise AxonOpsAuthError("Authentication failed")
            elif response.status_code == 404:
                raise AxonOpsNotFoundError(f"Resource not found: {endpoint}")
            elif response.status_code >= 400:
                logger.error(
                    "API Error Response",
                    status_code=response.status_code,
                    response_text=response.text,
                    url=url,
                    method=method
                )
                raise AxonOpsAPIError(
                    f"API error: {response.status_code} - {response.text}"
                )
            
            return response.json() if response.text else {}
            
        except requests.exceptions.ConnectionError as e:
            raise AxonOpsConnectionError(f"Failed to connect to API: {e}")
        except requests.exceptions.Timeout as e:
            raise AxonOpsConnectionError(f"Request timed out: {e}")
        except requests.exceptions.RequestException as e:
            raise AxonOpsAPIError(f"Request failed: {e}")
    
    # Organization and Cluster Methods
    
    def get_organizations(self) -> List[Dict[str, Any]]:
        """Get list of organizations"""
        result = self._request("GET", "/api/v1/orgs")
        return result.get("orgs", [])
    
    def get_cluster_settings(self, org: str, cluster_type: str, cluster: str) -> Dict[str, Any]:
        """Get cluster settings"""
        return self._request(
            "GET",
            f"/api/v1/clusterSettings/{org}/{cluster_type}/{cluster}",
            org=org
        )
    
    def get_nodes(self, org: str, cluster_type: str, cluster: str) -> List[Dict[str, Any]]:
        """Get cluster nodes"""
        return self._request(
            "GET",
            f"/api/v1/nodes/{org}/{cluster_type}/{cluster}",
            org=org
        )
    
    def get_nodes_full(self, org: str, cluster_type: str, cluster: str) -> List[Dict[str, Any]]:
        """Get cluster nodes with full details"""
        return self._request(
            "GET",
            f"/api/v1/nodes-full/{org}/{cluster_type}/{cluster}",
            org=org
        )
    
    # Metrics Methods
    
    def query(self, query: str, time: Optional[datetime] = None) -> Dict[str, Any]:
        """Execute Prometheus query"""
        if time is None:
            time = datetime.utcnow()
        
        # AxonOps requires both start and end parameters even for instant queries
        params = {
            "query": query,
            "start": int(time.timestamp()),
            "end": int(time.timestamp()),
            "time": int(time.timestamp())
        }
        
        return self._request("GET", "/api/v1/query", params=params)
    
    def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "60s"
    ) -> Dict[str, Any]:
        """Execute Prometheus range query"""
        params = {
            "query": query,
            "start": int(start.timestamp()),
            "end": int(end.timestamp()),
            "step": step,
        }
        
        return self._request("GET", "/api/v1/query_range", params=params)
    
    def get_metric_names(self, org: str, cluster_type: str, cluster: str) -> List[str]:
        """Get available metric names for a cluster"""
        result = self._request(
            "GET",
            f"/api/v1/metricNames/{org}/{cluster_type}/{cluster}",
            org=org
        )
        return result if isinstance(result, list) else []
    
    # Cassandra-specific Methods
    
    def get_keyspaces(self, org: str, cluster_type: str, cluster: str) -> List[Dict[str, Any]]:
        """Get Cassandra keyspaces"""
        return self._request(
            "GET",
            f"/api/v1/keyspaces/{org}/{cluster_type}/{cluster}",
            org=org
        )
    
    def get_snapshots(
        self,
        org: str,
        cluster_type: str,
        cluster: str,
        page: int = 1,
        per_page: int = 100
    ) -> Dict[str, Any]:
        """Get Cassandra snapshots"""
        params = {
            "page": page,
            "perPage": per_page,
        }
        return self._request(
            "GET",
            f"/api/v1/cassandraSnapshot/{org}/{cluster_type}/{cluster}",
            org=org,
            params=params
        )
    
    # Events Methods
    
    def get_events(
        self,
        org: str,
        cluster_type: str,
        cluster: str,
        start_time: datetime,
        end_time: datetime,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Get cluster events"""
        params = {
            "start": int(start_time.timestamp()),
            "end": int(end_time.timestamp()),
            "sort": "desc"
        }
        
        endpoint = f"/api/v1/events/{org}/{cluster_type}/{cluster}"
        
        # Always use POST with proper payload structure
        payload = {
            "f1": "",
            "f2": "",
            "host_id": "",
            "bucket": 25,
            "type": "",
            "level": "",
            "source": "",
            "message": "",
            "search_after": None
        }
        
        # Update payload with any provided filters
        if filters:
            payload.update(filters)
        
        # Log the full request details for debugging
        full_url = f"{self.api_url}{endpoint}"
        
        # Build the complete URL with query parameters
        url_with_params = f"{full_url}?start={params['start']}&end={params['end']}&sort={params['sort']}"
        
        # Generate curl equivalent for debugging
        import json
        curl_command = f"""curl -X POST "{url_with_params}" \\
  -H "Authorization: Bearer {self.token}" \\
  -H "Content-Type: application/json" \\
  -H "X-Grafana-Org-Id: {org}" \\
  -d '{json.dumps(payload)}' \\
  --max-time {self.timeout}"""
        
        logger.info(
            "Making events API request",
            url=full_url,
            url_with_params=url_with_params,
            params=params,
            payload=payload,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            time_range_hours=(end_time - start_time).total_seconds() / 3600,
            curl_equivalent=curl_command
        )
        
        try:
            response = self._request("POST", endpoint, org=org, params=params, json=payload)
        except Exception as e:
            # Log additional details on error
            logger.error(
                "Events API request failed",
                url=full_url,
                params=params,
                payload=payload,
                start_timestamp=int(start_time.timestamp()),
                end_timestamp=int(end_time.timestamp()),
                time_range_hours=(end_time - start_time).total_seconds() / 3600,
                error=str(e)
            )
            raise
        
        # Handle response format
        if isinstance(response, dict) and "data" in response:
            # AxonOps returns data as array directly
            data = response["data"]
            if isinstance(data, list):
                return data
            else:
                return []
        elif isinstance(response, list):
            return response
        else:
            return []
    
    def search_logs(
        self,
        org: str,
        cluster_type: str,
        cluster: str,
        start_time: datetime,
        end_time: datetime,
        message_filter: str,
        level: str = "",
        event_type: str = "",
        host_id: str = "",
        source: str = "",
        bucket: int = 25
    ) -> List[Dict[str, Any]]:
        """Search logs with specific message filter"""
        params = {
            "start": int(start_time.timestamp()),
            "end": int(end_time.timestamp()),
            "sort": "desc"
        }
        
        payload = {
            "type": event_type,
            "f1": "",
            "f2": "",
            "host_id": host_id,
            "level": level,
            "source": source,
            "message": message_filter,
            "bucket": bucket,
            "search_after": None
        }
        
        endpoint = f"/api/v1/events/{org}/{cluster_type}/{cluster}"
        response = self._request("POST", endpoint, org=org, params=params, json=payload)
        
        # Handle response format
        if isinstance(response, dict) and "data" in response:
            # AxonOps returns data as array directly, not wrapped in "events"
            data = response["data"]
            if isinstance(data, list):
                return data
            else:
                return []
        elif isinstance(response, list):
            return response
        elif response is None:
            return []
        else:
            return []
    
    def get_logs_histogram(
        self,
        org: str,
        cluster_type: str,
        cluster: str,
        start_time: datetime,
        end_time: datetime,
        message_filter: str,
        level: str = "",
        event_type: str = "",
        host_id: str = "",
        source: str = "",
        bucket: int = 25
    ) -> Dict[str, Any]:
        """Get histogram of log events over time"""
        params = {
            "start": int(start_time.timestamp()),
            "end": int(end_time.timestamp())
        }
        
        payload = {
            "type": event_type,
            "f1": "",
            "f2": "",
            "host_id": host_id,
            "level": level,
            "source": source,
            "message": message_filter,
            "bucket": bucket
        }
        
        endpoint = f"/api/v1/histogram/{org}/{cluster_type}/{cluster}"
        response = self._request("POST", endpoint, org=org, params=params, json=payload)
        
        # Return the response as-is since histogram format is consistent
        return response if response else {}
    
    # Agent Configuration Methods
    
    def get_agent_config(self, org: str, cluster_type: str, cluster: str) -> Dict[str, Any]:
        """Get agent configuration"""
        return self._request(
            "GET",
            f"/api/v1/agentconfig/{org}/{cluster_type}/{cluster}",
            org=org
        )
    
    # Utility Methods
    
    def health_check(self) -> bool:
        """Check if API is healthy"""
        try:
            self._request("GET", "/api/v1/healthz")
            return True
        except Exception:
            return False
    
    def get_server_time(self) -> int:
        """Get server time in UTC"""
        result = self._request("GET", "/api/v1/time")
        return result.get("timeUTC", 0)