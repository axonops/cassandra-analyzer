## Security Configuration

{% for rec in recommendations %}
### {{ rec.title }}

**Priority:** {{ rec.severity | severity_icon }} {{ rec.severity.value.upper() }}  
**Current Configuration:** {{ rec.current_value if rec.current_value else 'See details below' }}

{{ rec.description }}

{% if 'authentication' in rec.title.lower() %}
#### Authentication Status

Authentication controls who can connect to your cluster.

**Current Settings:**
{{ rec.current_value }}

{% if rec.severity.value == 'CRITICAL' %}
⚠️ **SECURITY RISK**: Your cluster is currently accessible without authentication. This allows anyone with network access to:
- Read all data
- Modify or delete data  
- Change cluster configuration
- Access sensitive system tables
{% endif %}

---

_**Enabling Authentication Checklist**:_
1. Increase `system_auth` keyspace replication factor
2. Create custom superuser account
3. Set authentication in `cassandra.yaml`
4. Restart nodes (rolling restart)
5. Disable default `cassandra` user
6. Update all client applications

---

{% elif 'authorization' in rec.title.lower() %}
#### Authorization Configuration

Authorization controls what authenticated users can do.

**Current State:** {{ rec.current_value }}

**Permission Levels:**
- `CREATE`: Create keyspaces/tables
- `ALTER`: Modify schemas
- `DROP`: Delete keyspaces/tables
- `SELECT`: Read data
- `MODIFY`: Write/delete data
- `AUTHORIZE`: Grant permissions

---

_**Best Practices**:_
- Use role-based access control (RBAC)
- Grant minimal required permissions
- Regular permission audits
- Separate roles for applications vs. administrators

---

{% elif 'encryption' in rec.title.lower() %}
#### Encryption Settings

Protects data in transit between clients/nodes.

**Current Configuration:** {{ rec.current_value }}

**Encryption Types:**
- **Client-to-Node**: Application connections
- **Node-to-Node**: Inter-cluster communication

---

_**Implementation Guide**:_
1. Generate SSL certificates
2. Configure `server_encryption_options`
3. Configure `client_encryption_options`
4. Test with `cqlsh --ssl`
5. Update all client connections

_Performance impact is typically < 10% with modern CPUs._

---

{% elif 'audit' in rec.title.lower() %}
#### Audit Logging

Tracks security-relevant events for compliance and forensics.

**Current Status:** {{ rec.current_value }}

**Auditable Events:**
- Authentication attempts
- Authorization failures
- DDL operations (CREATE, ALTER, DROP)
- DML operations (SELECT, INSERT, UPDATE, DELETE)
- Role/permission changes

---

_**Consideration**: Audit logging can generate significant data volume. Plan for:_
- Log rotation and retention
- Performance impact (typically 5-15%)
- Integration with SIEM systems
- Regular audit log reviews

---
{% endif %}

**Security Impact:** {{ rec.impact if rec.impact else 'May expose cluster to unauthorized access or compliance violations' }}

**Required Action:** {{ rec.recommendation }}

{% if rec.severity.value == 'CRITICAL' %}
---

**⚠️ IMMEDIATE ACTION REQUIRED**: This security issue should be addressed within 24 hours to prevent potential data breaches or unauthorized access.

---
{% endif %}

{% if rec.reference_url %}
🔐 **Security Guide:** [{{ rec.reference_url }}]({{ rec.reference_url }})
{% endif %}

---

{% endfor %}