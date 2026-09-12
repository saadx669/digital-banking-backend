import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client

from backend.fraud import calculate_fraud_score


# ============================================================
# ENVIRONMENT
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is missing from .env")

if not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_KEY is missing from .env")


# ============================================================
# SUPABASE
# ============================================================

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="Digital Banking Backend",
    description="Digital Banking Backend with transfers, withdrawals, fraud detection, fraud holds and human approval",
    version="1.2.0"
)


# ============================================================
# REQUEST MODELS
# ============================================================

class TransferRequest(BaseModel):
    idempotency_key: str
    from_account_number: str
    to_account_number: str
    amount: float
    initiated_by: str

    # Fraud signals - evaluated synchronously inside transfer_money
    # before any funds move. Default to False if the caller (e.g. an
    # n8n workflow doing frequency/location checks) doesn't supply them.
    new_recipient: bool = False
    unusual_frequency: bool = False
    unusual_location: bool = False
    unusual_time: bool = False
    suspicious_pattern: bool = False


class WithdrawalRequest(BaseModel):
    idempotency_key: str
    account_number: str
    amount: float
    initiated_by: str

    new_recipient: bool = False
    unusual_frequency: bool = False
    unusual_location: bool = False
    unusual_time: bool = False
    suspicious_pattern: bool = False


class ConsentRequest(BaseModel):
    customer_id: str
    decision: str  # "APPROVED" or "REJECTED"
    reason: str | None = None

    # Same fraud signals, re-evaluated at the moment consensus is
    # reached and funds are about to actually move.
    new_recipient: bool = False
    unusual_frequency: bool = False
    unusual_location: bool = False
    unusual_time: bool = False
    suspicious_pattern: bool = False


class FraudCheckRequest(BaseModel):
    transaction_id: str
    account_number: str
    amount: float

    new_recipient: bool = False
    unusual_frequency: bool = False
    unusual_location: bool = False
    unusual_time: bool = False
    suspicious_pattern: bool = False


class ApprovalDecisionRequest(BaseModel):
    decided_by: str
    reason: str = "Human review decision"


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():
    return {
        "message": "Digital Banking Backend is running"
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


# ============================================================
# GET ACCOUNTS
# ============================================================

@app.get("/accounts")
def get_accounts():

    try:

        response = (
            supabase
            .table("accounts")
            .select("*")
            .execute()
        )

        return {
            "success": True,
            "accounts": response.data
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Account fetch error: {str(e)}"
        )


# ============================================================
# TRANSFER
# ============================================================

@app.post("/transfer")
def transfer(request: TransferRequest):

    try:

        response = supabase.rpc(
            "transfer_money",
            {
                "p_idempotency_key": request.idempotency_key,
                "p_from_account_number": request.from_account_number,
                "p_to_account_number": request.to_account_number,
                "p_amount": request.amount,
                "p_initiated_by": request.initiated_by,
                "p_new_recipient": request.new_recipient,
                "p_unusual_frequency": request.unusual_frequency,
                "p_unusual_location": request.unusual_location,
                "p_unusual_time": request.unusual_time,
                "p_suspicious_pattern": request.suspicious_pattern
            }
        ).execute()

        result = response.data

        # A JOINT account under BOTH_SIGNATURES/MAJORITY authority comes
        # back PENDING - no funds moved yet, co-signers still need to act.
        if result and result[0].get("transaction_status") == "PENDING":
            return {
                "success": True,
                "result": result,
                "note": "Awaiting co-signer approval. Use POST /transactions/{id}/consent."
            }

        return {
            "success": True,
            "result": result
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Transfer error: {str(e)}"
        )


# ============================================================
# WITHDRAW
# ============================================================

@app.post("/withdraw")
def withdraw(request: WithdrawalRequest):

    try:

        response = supabase.rpc(
            "withdraw_money",
            {
                "p_idempotency_key": request.idempotency_key,
                "p_account_number": request.account_number,
                "p_amount": request.amount,
                "p_initiated_by": request.initiated_by,
                "p_new_recipient": request.new_recipient,
                "p_unusual_frequency": request.unusual_frequency,
                "p_unusual_location": request.unusual_location,
                "p_unusual_time": request.unusual_time,
                "p_suspicious_pattern": request.suspicious_pattern
            }
        ).execute()

        result = response.data

        if result and result[0].get("transaction_status") == "PENDING":
            return {
                "success": True,
                "result": result,
                "note": "Awaiting co-signer approval. Use POST /transactions/{id}/consent."
            }

        return {
            "success": True,
            "result": result
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Withdrawal error: {str(e)}"
        )


# ============================================================
# GET TRANSACTION
# ============================================================

@app.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str):

    try:

        response = (
            supabase
            .table("transactions")
            .select("*")
            .eq("id", transaction_id)
            .limit(1)
            .execute()
        )

        if not response.data:

            raise HTTPException(
                status_code=404,
                detail="Transaction not found"
            )

        return {
            "success": True,
            "transaction": response.data[0]
        }

    except HTTPException:
        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Transaction fetch error: {str(e)}"
        )


# ============================================================
# GET TRANSACTION CONSENTS (who has approved/rejected so far)
# ============================================================

@app.get("/transactions/{transaction_id}/consents")
def get_transaction_consents(transaction_id: str):

    try:

        response = (
            supabase
            .table("transaction_consents")
            .select("*")
            .eq("transaction_id", transaction_id)
            .execute()
        )

        return {
            "success": True,
            "consents": response.data
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Consent fetch error: {str(e)}"
        )


# ============================================================
# RECORD A CO-SIGNER'S CONSENT ON A JOINT TRANSACTION
# ============================================================

@app.post("/transactions/{transaction_id}/consent")
def record_transaction_consent(transaction_id: str, request: ConsentRequest):

    try:

        response = supabase.rpc(
            "record_transaction_consent",
            {
                "p_transaction_id": transaction_id,
                "p_customer_id": request.customer_id,
                "p_decision": request.decision,
                "p_reason": request.reason,
                "p_new_recipient": request.new_recipient,
                "p_unusual_frequency": request.unusual_frequency,
                "p_unusual_location": request.unusual_location,
                "p_unusual_time": request.unusual_time,
                "p_suspicious_pattern": request.suspicious_pattern
            }
        ).execute()

        return {
            "success": True,
            "result": response.data
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Consent error: {str(e)}"
        )


# ============================================================
# FRAUD CHECK
# ============================================================

@app.post("/fraud/check")
def fraud_check(request: FraudCheckRequest):

    try:

        # ----------------------------------------------------
        # 1. FIND ACCOUNT
        # ----------------------------------------------------

        account_response = (
            supabase
            .table("accounts")
            .select("id, account_number")
            .eq("account_number", request.account_number)
            .limit(1)
            .execute()
        )

        if not account_response.data:

            raise HTTPException(
                status_code=404,
                detail="Account not found"
            )

        account = account_response.data[0]


        # ----------------------------------------------------
        # 2. FIND TRANSACTION
        # ----------------------------------------------------

        transaction_response = (
            supabase
            .table("transactions")
            .select("id, amount, status")
            .eq("id", request.transaction_id)
            .limit(1)
            .execute()
        )

        if not transaction_response.data:

            raise HTTPException(
                status_code=404,
                detail="Transaction not found"
            )

        transaction = transaction_response.data[0]


        # ----------------------------------------------------
        # 3. USE ACTUAL DATABASE TRANSACTION AMOUNT
        # ----------------------------------------------------

        actual_amount = float(transaction["amount"])


        # ----------------------------------------------------
        # 4. CALCULATE FRAUD SCORE
        # ----------------------------------------------------

        result = calculate_fraud_score(
            amount=actual_amount,
            new_recipient=request.new_recipient,
            unusual_frequency=request.unusual_frequency,
            unusual_location=request.unusual_location,
            unusual_time=request.unusual_time,
            suspicious_pattern=request.suspicious_pattern
        )


        # ----------------------------------------------------
        # 5. PREPARE FRAUD ALERT
        # ----------------------------------------------------

        fraud_alert_data = {
            "transaction_id": request.transaction_id,
            "account_id": account["id"],
            "fraud_score": result["fraud_score"],
            "risk_level": result["risk_level"],
            "reasons": result["reasons"],
            "status": "OPEN"
        }


        # ----------------------------------------------------
        # 6. CHECK EXISTING FRAUD ALERT
        # ----------------------------------------------------

        existing_alert_response = (
            supabase
            .table("fraud_alerts")
            .select("*")
            .eq("transaction_id", request.transaction_id)
            .limit(1)
            .execute()
        )


        # ----------------------------------------------------
        # 7. UPDATE EXISTING ALERT
        # ----------------------------------------------------

        if existing_alert_response.data:

            existing_alert = existing_alert_response.data[0]

            alert_response = (
                supabase
                .table("fraud_alerts")
                .update(fraud_alert_data)
                .eq("id", existing_alert["id"])
                .execute()
            )

            fraud_alert_action = "UPDATED"


        # ----------------------------------------------------
        # 8. CREATE NEW ALERT
        # ----------------------------------------------------

        else:

            alert_response = (
                supabase
                .table("fraud_alerts")
                .insert(fraud_alert_data)
                .execute()
            )

            fraud_alert_action = "CREATED"


        # ----------------------------------------------------
        # 9. HIGH RISK → CREATE HOLD + APPROVAL
        # ----------------------------------------------------

        hold_result = None

        if result["risk_level"] == "HIGH":

            reason = "; ".join(result["reasons"])

            hold_response = supabase.rpc(
                "create_fraud_hold",
                {
                    "p_transaction_id": request.transaction_id,
                    "p_account_id": account["id"],
                    "p_amount": actual_amount,
                    "p_fraud_score": result["fraud_score"],
                    "p_reason": reason
                }
            ).execute()

            hold_result = hold_response.data


        # ----------------------------------------------------
        # 10. RETURN FRAUD RESULT
        # ----------------------------------------------------

        return {
            "success": True,
            "transaction_id": request.transaction_id,
            "account_number": request.account_number,
            "amount_used_for_fraud_check": actual_amount,
            "fraud_score": result["fraud_score"],
            "risk_level": result["risk_level"],
            "action": result["action"],
            "human_approval_required": result["human_approval_required"],
            "reasons": result["reasons"],
            "fraud_alert_action": fraud_alert_action,
            "fraud_alert": alert_response.data,
            "hold_workflow": hold_result
        }


    except HTTPException:
        raise


    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Fraud check error: {str(e)}"
        )


# ============================================================
# APPROVE FRAUD HOLD
# ============================================================

@app.post("/approvals/{approval_id}/approve")
def approve_fraud_hold(
    approval_id: str,
    request: ApprovalDecisionRequest
):

    try:

        response = supabase.rpc(
            "approve_fraud_hold",
            {
                "p_approval_id": approval_id,
                "p_decided_by": request.decided_by,
                "p_reason": request.reason
            }
        ).execute()

        return {
            "success": True,
            "result": response.data
        }


    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Approval error: {str(e)}"
        )


# ============================================================
# REJECT FRAUD HOLD
# ============================================================

@app.post("/approvals/{approval_id}/reject")
def reject_fraud_hold(
    approval_id: str,
    request: ApprovalDecisionRequest
):

    try:

        response = supabase.rpc(
            "reject_fraud_hold",
            {
                "p_approval_id": approval_id,
                "p_decided_by": request.decided_by,
                "p_reason": request.reason
            }
        ).execute()

        return {
            "success": True,
            "result": response.data
        }


    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Rejection error: {str(e)}"
        )
