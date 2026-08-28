import httpx
from typing import Dict, List

from app.core.cache import cache
from app.core.config import settings
from app.core.logging import get_logger


logger = get_logger(__name__)


class PaystackHospitalPayments:
    BASE = "https://api.paystack.co"

    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }

    async def get_banks(self) -> List[Dict]:
        cached = cache.get("paystack:banks:NG")
        if cached:
            return cached
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{self.BASE}/bank?country=nigeria", headers=self.headers)
            data = resp.json()
        if not data.get("status"):
            raise Exception(f"Paystack bank list failed: {data.get('message')}")
        banks = [{"name": b["name"], "code": b["code"]} for b in data.get("data", [])]
        cache.set("paystack:banks:NG", banks, ttl=7 * 24 * 60 * 60)
        return banks

    async def resolve_account(self, account_number: str, bank_code: str) -> Dict:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{self.BASE}/bank/resolve",
                headers=self.headers,
                params={"account_number": account_number, "bank_code": bank_code},
            )
            data = resp.json()
        if not data.get("status"):
            raise Exception(f"Paystack account resolve failed: {data.get('message')}")
        return data["data"]

    async def create_transfer_recipient(
        self,
        business_name: str,
        account_number: str,
        bank_code: str,
    ) -> Dict:
        payload = {
            "type": "nuban",
            "name": business_name,
            "account_number": account_number,
            "bank_code": bank_code,
            "currency": "NGN",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{self.BASE}/transferrecipient", headers=self.headers, json=payload)
            data = resp.json()
        if not data.get("status"):
            raise Exception(f"Paystack recipient creation failed: {data.get('message')}")
        return data["data"]

    async def initialize_booking_transaction(
        self,
        email: str,
        amount_kobo: int,
        reference: str,
        metadata: Dict,
        callback_url: str,
    ) -> Dict:
        payload = {
            "email": email,
            "amount": amount_kobo,
            "reference": reference,
            "metadata": metadata,
            "callback_url": callback_url,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{self.BASE}/transaction/initialize", headers=self.headers, json=payload)
            data = resp.json()
        if not data.get("status"):
            raise Exception(f"Paystack initialize failed: {data.get('message')}")
        return data["data"]

    async def verify_transaction(self, reference: str) -> Dict:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{self.BASE}/transaction/verify/{reference}", headers=self.headers)
            data = resp.json()
        if not data.get("status"):
            raise Exception(f"Paystack verify failed: {data.get('message')}")
        return data["data"]

    async def initiate_transfer(self, amount_kobo: int, recipient_code: str, reason: str, reference: str) -> Dict:
        # `reference` must be caller-supplied and stable across retries (e.g.
        # derived from the payout id) — Paystack deduplicates transfers by
        # reference, which is what makes a retry after a client-side timeout
        # safe instead of double-paying the recipient.
        payload = {
            "source": "balance",
            "amount": amount_kobo,
            "recipient": recipient_code,
            "reason": reason,
            "reference": reference,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{self.BASE}/transfer", headers=self.headers, json=payload)
            data = resp.json()
        if not data.get("status"):
            raise Exception(f"Paystack transfer failed: {data.get('message')}")
        return data["data"]

    async def verify_transfer(self, reference: str) -> Dict:
        """
        Look up a transfer's real status by reference. Used after a
        "duplicate reference" error to find out whether an earlier attempt
        actually went through, instead of assuming it failed.
        """
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{self.BASE}/transfer/verify/{reference}", headers=self.headers)
            data = resp.json()
        if not data.get("status"):
            raise Exception(f"Paystack transfer verify failed: {data.get('message')}")
        return data["data"]


hospital_payments = PaystackHospitalPayments()


def clinic_has_payout_destination(db, clinic_id: str) -> bool:
    """
    True when the clinic has an active, verified bank account with a Paystack
    transfer recipient — i.e. money collected from a patient can actually be
    forwarded to the clinic automatically (send_payout_to_hospital). Patient
    payment collection on the public booking page is gated on this so Vitar
    never ends up holding patient money it has no automated way to pay out.
    """
    from app.models.models import HospitalBankAccount

    acct = (
        db.query(HospitalBankAccount)
        .filter(
            HospitalBankAccount.hospital_id == clinic_id,
            HospitalBankAccount.active.is_(True),
            HospitalBankAccount.verified.is_(True),
        )
        .first()
    )
    return bool(acct and acct.paystack_recipient_code)
