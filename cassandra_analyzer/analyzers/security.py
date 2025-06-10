"""
Security analyzer - checks security configuration and best practices
"""

from typing import Dict, Any, List
from ..models import ClusterState, Recommendation, Severity
from .base import BaseAnalyzer


class SecurityAnalyzer(BaseAnalyzer):
    """Analyzes security aspects of the cluster"""
    
    def analyze(self, cluster_state: ClusterState) -> Dict[str, Any]:
        """Analyze security configuration"""
        recommendations = []
        summary = {}
        details = {}
        
        # Analyze authentication/authorization
        auth_recommendations, auth_details = self._analyze_auth(cluster_state)
        recommendations.extend(auth_recommendations)
        details.update(auth_details)
        
        # Analyze encryption
        recommendations.extend(self._analyze_encryption(cluster_state))
        
        # Create summary
        summary = {
            "recommendations_count": len(recommendations),
            "auth_enabled": details.get("auth_enabled", False),
            "authz_enabled": details.get("authz_enabled", False),
            "authenticator": details.get("authenticator", "Unknown"),
            "authorizer": details.get("authorizer", "Unknown")
        }
        
        return {
            "recommendations": [r.dict() for r in recommendations],
            "summary": summary,
            "details": details
        }
    
    def _analyze_auth(self, cluster_state: ClusterState) -> tuple[List[Recommendation], Dict[str, Any]]:
        """Analyze authentication and authorization settings"""
        recommendations = []
        
        # Check authentication settings from node configuration
        auth_disabled_nodes = []
        authz_disabled_nodes = []
        auth_configs = {}
        authz_configs = {}
        
        for node_id, node in cluster_state.nodes.items():
            if hasattr(node, 'Details') and node.Details:
                # Check authenticator
                authenticator = node.Details.get('comp_authenticator', 'Unknown')
                if authenticator not in auth_configs:
                    auth_configs[authenticator] = []
                auth_configs[authenticator].append(node_id)
                
                if authenticator == 'AllowAllAuthenticator':
                    auth_disabled_nodes.append(node_id)
                
                # Check authorizer
                authorizer = node.Details.get('comp_authorizer', 'Unknown')
                if authorizer not in authz_configs:
                    authz_configs[authorizer] = []
                authz_configs[authorizer].append(node_id)
                
                if authorizer == 'AllowAllAuthorizer':
                    authz_disabled_nodes.append(node_id)
        
        # Check for authentication issues
        if auth_disabled_nodes:
            recommendations.append(
                self._create_recommendation(
                    title="Authentication Disabled",
                    description=f"Authentication is disabled on {len(auth_disabled_nodes)} node(s)",
                    severity=Severity.CRITICAL,
                    category="security",
                    impact="Anyone can connect to the database without credentials",
                    recommendation="Enable PasswordAuthenticator or another secure authenticator",
                    current_value="AllowAllAuthenticator",
                    affected_nodes=auth_disabled_nodes
                )
            )
        elif 'PasswordAuthenticator' in auth_configs:
            # Authentication is properly configured
            pass  # No recommendation needed
        
        # Check for authorization issues
        if authz_disabled_nodes:
            recommendations.append(
                self._create_recommendation(
                    title="Authorization Disabled",
                    description=f"Authorization is disabled on {len(authz_disabled_nodes)} node(s)",
                    severity=Severity.CRITICAL,
                    category="security",
                    impact="All authenticated users have full access to all data",
                    recommendation="Enable CassandraAuthorizer for role-based access control",
                    current_value="AllowAllAuthorizer",
                    affected_nodes=authz_disabled_nodes
                )
            )
        elif 'CassandraAuthorizer' in authz_configs:
            # Authorization is properly configured
            pass  # No recommendation needed
        
        # Check for inconsistent auth configuration
        if len(auth_configs) > 1:
            recommendations.append(
                self._create_recommendation(
                    title="Inconsistent Authentication Configuration",
                    description=f"Different authenticators configured across nodes: {list(auth_configs.keys())}",
                    severity=Severity.CRITICAL,
                    category="security",
                    impact="Inconsistent security policies across the cluster",
                    recommendation="Ensure all nodes use the same authenticator",
                    auth_configs={k: len(v) for k, v in auth_configs.items()}
                )
            )
        
        if len(authz_configs) > 1:
            recommendations.append(
                self._create_recommendation(
                    title="Inconsistent Authorization Configuration",
                    description=f"Different authorizers configured across nodes: {list(authz_configs.keys())}",
                    severity=Severity.CRITICAL,
                    category="security",
                    impact="Inconsistent access control across the cluster",
                    recommendation="Ensure all nodes use the same authorizer",
                    authz_configs={k: len(v) for k, v in authz_configs.items()}
                )
            )
        
        # Determine overall auth status
        auth_enabled = 'PasswordAuthenticator' in auth_configs or len(auth_configs) == 0
        authz_enabled = 'CassandraAuthorizer' in authz_configs or len(authz_configs) == 0
        
        # Get the most common authenticator/authorizer
        authenticator = max(auth_configs.keys(), key=lambda k: len(auth_configs[k])) if auth_configs else "Unknown"
        authorizer = max(authz_configs.keys(), key=lambda k: len(authz_configs[k])) if authz_configs else "Unknown"
        
        details = {
            "auth_enabled": auth_enabled and authenticator != 'AllowAllAuthenticator',
            "authz_enabled": authz_enabled and authorizer != 'AllowAllAuthorizer',
            "authenticator": authenticator,
            "authorizer": authorizer
        }
        
        return recommendations, details
    
    def _analyze_encryption(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze encryption settings"""
        recommendations = []
        
        # This would check for encryption settings
        recommendations.append(
            self._create_recommendation(
                title="Review Encryption Configuration",
                description="Verify that appropriate encryption is configured",
                severity=Severity.INFO,
                category="security",
                impact="Data transmitted in clear text",
                recommendation="Enable client-to-node and node-to-node encryption"
            )
        )
        
        return recommendations