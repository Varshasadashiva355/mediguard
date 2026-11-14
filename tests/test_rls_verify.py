"""
MediGuard AI – Pytest integration for RLS and RBAC verification
"""
from scripts.rls_verify import verify_sql_rls_declarations, verify_active_rbac_enforcement

def test_rls_sql_declarations():
    verify_sql_rls_declarations()

def test_rls_rbac_active_enforcement():
    verify_active_rbac_enforcement()
