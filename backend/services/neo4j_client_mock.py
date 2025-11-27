from typing import List, Dict
from datetime import datetime

from backend.models import RuleDefinition


def run_rule(rule: RuleDefinition) -> List[Dict]:
    """
    Mock detection results for a rule.
    """
    detections: List[Dict] = []

    if "mule" in rule.name.lower():
        detections.append(
            {
                "subject_account_number": "GCASH-100123",
                "subject_customer_name": "Juan Dela Cruz",
                "severity": "CRITICAL",
                "summary": "Account GCASH-100123 linked to 3 mule accounts",
                "network_summary": "Subject account connected to 3 mule accounts via device DEV-12345 within 24 hours.",
                "linked_accounts": [
                    {"account_number": "GCASH-200001", "customer_name": "Mule Account 1", "role": "mule"},
                    {"account_number": "GCASH-200002", "customer_name": "Mule Account 2", "role": "mule"},
                    {"account_number": "GCASH-200003", "customer_name": "Mule Account 3", "role": "mule"},
                ],
                "linked_devices": [
                    {"device_id": "DEV-12345", "description": "Android device shared across mule ring", "device_type": "Android"}
                ],
                "details": {"pattern": "shared_device", "detected_at": datetime.utcnow().isoformat()},
            }
        )
    if "identity" in rule.name.lower():
        detections.append(
            {
                "subject_account_number": "GCASH-300001",
                "subject_customer_name": "Maria Santos",
                "severity": "HIGH",
                "summary": "Identity mismatch detected on account GCASH-300001",
                "network_summary": "New device DEV-54321 used for high-risk transactions across multiple accounts.",
                "linked_accounts": [
                    {"account_number": "GCASH-300002", "customer_name": "Maria Santos", "role": "duplicate_identity"},
                ],
                "linked_devices": [
                    {"device_id": "DEV-54321", "description": "iOS device seen across multiple identities", "device_type": "iOS"}
                ],
                "details": {"pattern": "identity_fraud", "detected_at": datetime.utcnow().isoformat()},
            }
        )

    # Default detection if rule not matched above
    if not detections:
        detections.append(
            {
                "subject_account_number": "GCASH-999999",
                "subject_customer_name": "Demo Account",
                "severity": "MEDIUM",
                "summary": f"Generic alert for rule {rule.name}",
                "network_summary": "Demo network summary placeholder.",
                "linked_accounts": [],
                "linked_devices": [],
                "details": {"pattern": "generic", "detected_at": datetime.utcnow().isoformat()},
            }
        )

    return detections


def get_case_context(alert_id: int) -> Dict:
    """
    Return mock graph context for an alert.
    """
    return {
        "alert_id": alert_id,
        "subject_account": {"account_number": "GCASH-100123", "customer_name": "Juan Dela Cruz"},
        "linked_accounts": [
            {"account_number": "GCASH-200001", "role": "mule"},
            {"account_number": "GCASH-200002", "role": "mule"},
            {"account_number": "GCASH-200003", "role": "mule"},
        ],
        "linked_devices": [
            {"device_id": "DEV-12345", "description": "Shared Android device"}
        ],
    }
