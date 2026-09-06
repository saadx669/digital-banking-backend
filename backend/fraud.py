from typing import Dict, List


def calculate_fraud_score(
    amount: float,
    new_recipient: bool = False,
    unusual_frequency: bool = False,
    unusual_location: bool = False,
    unusual_time: bool = False,
    suspicious_pattern: bool = False,
) -> Dict:

    score = 0
    reasons: List[str] = []

    # --------------------------------------------------------
    # 1. Unusual transaction amount
    # --------------------------------------------------------

    if amount >= 500000:
        score += 30
        reasons.append("Very large transaction amount")

    elif amount >= 100000:
        score += 20
        reasons.append("Unusually large transaction amount")

    # --------------------------------------------------------
    # 2. New recipient
    # --------------------------------------------------------

    if new_recipient:
        score += 20
        reasons.append("New beneficiary")

    # --------------------------------------------------------
    # 3. Unusual frequency
    # --------------------------------------------------------

    if unusual_frequency:
        score += 20
        reasons.append("Unusual transaction frequency")

    # --------------------------------------------------------
    # 4. Unusual location
    # --------------------------------------------------------

    if unusual_location:
        score += 15
        reasons.append("Unusual transaction location")

    # --------------------------------------------------------
    # 5. Unusual time
    # --------------------------------------------------------

    if unusual_time:
        score += 10
        reasons.append("Transaction at unusual time")

    # --------------------------------------------------------
    # 6. Known suspicious pattern
    # --------------------------------------------------------

    if suspicious_pattern:
        score += 30
        reasons.append("Known suspicious transaction pattern")

    # Maximum score = 100
    score = min(score, 100)

    # --------------------------------------------------------
    # Risk classification
    # --------------------------------------------------------

    if score >= 70:
        risk_level = "HIGH"
        action = "HOLD"
        human_approval_required = True

    elif score >= 40:
        risk_level = "MEDIUM"
        action = "REVIEW"
        human_approval_required = True

    else:
        risk_level = "LOW"
        action = "ALLOW"
        human_approval_required = False

    return {
        "fraud_score": score,
        "risk_level": risk_level,
        "action": action,
        "human_approval_required": human_approval_required,
        "reasons": reasons,
    }