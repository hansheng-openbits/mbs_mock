from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from eth_account import Account
from web3 import Web3

try:
    from web3.middleware import geth_poa_middleware  # web3.py <7
except ImportError:  # web3.py >=7
    geth_poa_middleware = None
    try:
        from web3.middleware import ExtraDataToPOAMiddleware
    except ImportError:
        ExtraDataToPOAMiddleware = None

try:
    from rmbs_platform.config import settings
except ImportError:
    from config import settings


@dataclass(frozen=True)
class Web3Addresses:
    tranche_factory: str
    transfer_validator: str
    servicer_oracle: str
    waterfall_engine: str
    loan_nft: str = ""  # Optional: LoanNFT contract address


# Loan status enum mapping (matches LoanNFT.sol)
class LoanStatus:
    CURRENT = 0           # 0-29 DPD
    DELINQUENT_30 = 1     # 30-59 DPD
    DELINQUENT_60 = 2     # 60-89 DPD
    DELINQUENT_90 = 3     # 90+ DPD
    DEFAULT = 4           # Foreclosure initiated
    PAID_OFF = 5          # Fully paid
    PREPAID = 6           # Prepaid before maturity

    @staticmethod
    def from_dpd(dpd: int, is_defaulted: bool = False, is_paid_off: bool = False, is_prepaid: bool = False) -> int:
        """Convert days past due to LoanStatus enum value."""
        if is_defaulted:
            return LoanStatus.DEFAULT
        if is_paid_off:
            return LoanStatus.PAID_OFF
        if is_prepaid:
            return LoanStatus.PREPAID
        if dpd >= 90:
            return LoanStatus.DELINQUENT_90
        if dpd >= 60:
            return LoanStatus.DELINQUENT_60
        if dpd >= 30:
            return LoanStatus.DELINQUENT_30
        return LoanStatus.CURRENT

    @staticmethod
    def to_string(status: int) -> str:
        """Convert status enum to human-readable string."""
        names = {
            0: "Current",
            1: "30+ DPD",
            2: "60+ DPD",
            3: "90+ DPD",
            4: "Default",
            5: "Paid Off",
            6: "Prepaid",
        }
        return names.get(status, "Unknown")


class Web3Client:
    def __init__(self, rpc_url: str, private_key: str, addresses: Web3Addresses) -> None:
        self.rpc_url = rpc_url
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if geth_poa_middleware is not None:
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        elif ExtraDataToPOAMiddleware is not None:
            self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        if not private_key:
            raise ValueError("RMBS_WEB3_ADMIN_PRIVATE_KEY is required for Web3 transactions.")

        self.account = Account.from_key(private_key)
        self.w3.eth.default_account = self.account.address

        self.addresses = addresses
        self.tranche_factory = self._get_contract(addresses.tranche_factory, _TRANCHE_FACTORY_ABI)
        self.transfer_validator = self._get_contract(addresses.transfer_validator, _TRANSFER_VALIDATOR_ABI)
        self.servicer_oracle = self._get_contract(addresses.servicer_oracle, _SERVICER_ORACLE_ABI)
        self.waterfall_engine = self._get_contract(addresses.waterfall_engine, _WATERFALL_ENGINE_ABI)

    def is_connected(self) -> bool:
        return self.w3.is_connected()

    def register_deal(
        self,
        deal_id: str,
        deal_name: str,
        arranger: str,
        closing_date: int,
        maturity_date: int,
    ) -> str:
        deal_id_bytes = self._normalize_deal_id(deal_id)
        tx = self.tranche_factory.functions.registerDeal(
            deal_id_bytes,
            deal_name,
            Web3.to_checksum_address(arranger),
            closing_date,
            maturity_date,
        )
        return self._send_tx(tx)

    def list_deals(self) -> List[str]:
        deals = self.tranche_factory.functions.getAllDeals().call()
        return [self._bytes32_to_hex(deal_id) for deal_id in deals]

    def get_deal_info(self, deal_id: str) -> Dict[str, Any]:
        deal_id_bytes = self._normalize_deal_id(deal_id)
        info = self.tranche_factory.functions.getDealInfo(deal_id_bytes).call()
        return {
            "deal_id": self._bytes32_to_hex(info[0]),
            "deal_name": info[1],
            "arranger": info[2],
            "closing_date": int(info[3]),
            "maturity_date": int(info[4]),
            "is_active": bool(info[5]),
            "total_face_value": int(info[6]),
        }

    def get_tranches_for_deal(self, deal_id: str) -> List[str]:
        deal_id_bytes = self._normalize_deal_id(deal_id)
        return self.tranche_factory.functions.getTranchesForDeal(deal_id_bytes).call()

    def deploy_tranche(self, params: Dict[str, Any]) -> str:
        deal_id_bytes = self._normalize_deal_id(params["deal_id"])
        init_params = (
            deal_id_bytes,
            params["tranche_id"],
            params["name"],
            params["symbol"],
            int(params["original_face_value"]),
            int(params["coupon_rate_bps"]),
            int(params["payment_frequency"]),
            int(params["maturity_date"]),
            Web3.to_checksum_address(params["payment_token"]),
            Web3.to_checksum_address(params["transfer_validator"]),
            Web3.to_checksum_address(params["admin"]),
            Web3.to_checksum_address(params["issuer"]),
            Web3.to_checksum_address(params["trustee"]),
        )
        tx = self.tranche_factory.functions.deployTranche(init_params)
        return self._send_tx(tx)

    def update_investor(
        self,
        investor: str,
        jurisdiction: Optional[str],
        is_accredited: Optional[bool],
        kyc_expiration: Optional[int],
        sanctioned: Optional[bool],
        lockup_expiration: Optional[int],
    ) -> List[str]:
        tx_hashes: List[str] = []
        investor_address = Web3.to_checksum_address(investor)

        if kyc_expiration is not None:
            tx = self.transfer_validator.functions.setKYCStatusWithExpiry(
                investor_address,
                True,
                int(kyc_expiration),
            )
            tx_hashes.append(self._send_tx(tx))

        if is_accredited is not None:
            tx = self.transfer_validator.functions.setAccreditationStatus(
                investor_address,
                bool(is_accredited),
            )
            tx_hashes.append(self._send_tx(tx))

        if jurisdiction:
            jurisdiction_bytes = jurisdiction.encode("ascii")[:2]
            tx = self.transfer_validator.functions.setJurisdiction(
                investor_address,
                jurisdiction_bytes,
            )
            tx_hashes.append(self._send_tx(tx))

        if sanctioned is not None:
            tx = self.transfer_validator.functions.setSanctionsStatus(
                investor_address,
                bool(sanctioned),
            )
            tx_hashes.append(self._send_tx(tx))

        if lockup_expiration is not None:
            tx = self.transfer_validator.functions.setLockup(
                investor_address,
                int(lockup_expiration),
            )
            tx_hashes.append(self._send_tx(tx))

        return tx_hashes

    def submit_loan_tape(self, data: Dict[str, Any]) -> str:
        deal_id_bytes = self._normalize_deal_id(data["deal_id"])
        data_hash = data.get("data_hash") or ("0" * 64)
        zk_proof = data.get("zk_proof") or b""
        loan_tape = (
            deal_id_bytes,
            int(data["period_number"]),
            int(data["reporting_date"]),
            0,
            int(data["scheduled_principal"]),
            int(data["scheduled_interest"]),
            int(data["actual_principal"]),
            int(data["actual_interest"]),
            int(data.get("prepayments", 0)),
            int(data.get("curtailments", 0)),
            int(data.get("defaults", 0)),
            int(data.get("loss_severity", 0)),
            int(data.get("recoveries", 0)),
            int(data.get("total_loan_count", 0)),
            int(data.get("current_loan_count", 0)),
            int(data.get("delinquent_loan_count", 0)),
            int(data.get("total_upb", 0)),
            int(data.get("wac", 0)),
            int(data.get("wam", 0)),
            int(data.get("wa_ltv", 0)),
            bytes.fromhex(data_hash),
            zk_proof,
            False,
            False,
            Web3.to_checksum_address(self.account.address),
        )
        tx = self.servicer_oracle.functions.submitLoanTape(loan_tape)
        return self._send_tx(tx)

    def configure_waterfall(self, config: Dict[str, Any]) -> str:
        deal_id_bytes = self._normalize_deal_id(config["deal_id"])
        waterfall_config = (
            deal_id_bytes,
            Web3.to_checksum_address(config["payment_token"]),
            [Web3.to_checksum_address(addr) for addr in config["tranches"]],
            config["seniorities"],
            config["interest_rates_bps"],
            int(config.get("trustee_fees_bps", 0)),
            int(config.get("servicer_fees_bps", 0)),
            Web3.to_checksum_address(config["trustee_address"]),
            Web3.to_checksum_address(config["servicer_address"]),
            bool(config.get("principal_sequential", True)),
            True,
        )
        tx = self.waterfall_engine.functions.configureWaterfall(waterfall_config)
        return self._send_tx(tx)

    def execute_waterfall(self, deal_id: str, period_number: int) -> str:
        deal_id_bytes = self._normalize_deal_id(deal_id)
        tx = self.waterfall_engine.functions.executeWaterfall(deal_id_bytes, int(period_number))
        return self._send_tx(tx)

    # =========================================================================
    # LOAN NFT METHODS
    # =========================================================================

    def update_loan_nft_status(
        self,
        loan_nft_address: str,
        token_id: int,
        new_status: int,
        new_balance: int,
    ) -> str:
        """
        Update a single loan NFT's status (Servicer role).
        
        Parameters
        ----------
        loan_nft_address : str
            Address of the LoanNFT contract
        token_id : int
            Token ID of the loan NFT
        new_status : int
            New status (use LoanStatus enum values)
        new_balance : int
            Updated current balance in wei
        
        Returns
        -------
        str
            Transaction hash
        """
        loan_nft = self._get_contract(loan_nft_address, _LOAN_NFT_ABI)
        tx = loan_nft.functions.updateLoanStatus(
            int(token_id),
            int(new_status),
            int(new_balance),
        )
        return self._send_tx(tx)

    def update_loan_nfts_batch(
        self,
        loan_nft_address: str,
        token_ids: List[int],
        statuses: List[int],
        balances: List[int],
    ) -> str:
        """
        Batch update loan NFT statuses (gas efficient for monthly servicer tape).
        
        Parameters
        ----------
        loan_nft_address : str
            Address of the LoanNFT contract
        token_ids : list of int
            Array of token IDs
        statuses : list of int
            Array of new statuses (use LoanStatus enum values)
        balances : list of int
            Array of new balances in wei
        
        Returns
        -------
        str
            Transaction hash
        """
        if len(token_ids) != len(statuses) or len(token_ids) != len(balances):
            raise ValueError("Arrays must have equal length")
        if len(token_ids) > 100:
            raise ValueError("Maximum batch size is 100 (split into multiple calls)")
        
        loan_nft = self._get_contract(loan_nft_address, _LOAN_NFT_ABI)
        tx = loan_nft.functions.updateLoanStatusBatch(
            [int(tid) for tid in token_ids],
            [int(s) for s in statuses],
            [int(b) for b in balances],
        )
        return self._send_tx(tx)

    def get_loan_nft_metadata(self, loan_nft_address: str, token_id: int) -> Dict[str, Any]:
        """
        Get loan NFT metadata.
        
        Parameters
        ----------
        loan_nft_address : str
            Address of the LoanNFT contract
        token_id : int
            Token ID
        
        Returns
        -------
        dict
            Loan metadata including deal_id, loan_id, balances, status, etc.
        """
        loan_nft = self._get_contract(loan_nft_address, _LOAN_NFT_ABI)
        metadata = loan_nft.functions.getLoanMetadata(int(token_id)).call()
        return {
            "deal_id": self._bytes32_to_hex(metadata[0]),
            "loan_id": metadata[1],
            "original_balance": int(metadata[2]),
            "current_balance": int(metadata[3]),
            "note_rate": int(metadata[4]),
            "origination_date": int(metadata[5]),
            "maturity_date": int(metadata[6]),
            "status": int(metadata[7]),
            "status_name": LoanStatus.to_string(int(metadata[7])),
            "data_hash": self._bytes32_to_hex(metadata[8]),
            "last_updated": int(metadata[9]),
        }

    def get_loans_for_deal(self, loan_nft_address: str, deal_id: str) -> List[int]:
        """
        Get all loan token IDs for a deal.
        
        Parameters
        ----------
        loan_nft_address : str
            Address of the LoanNFT contract
        deal_id : str
            Deal identifier
        
        Returns
        -------
        list of int
            Token IDs for all loans in the deal
        """
        loan_nft = self._get_contract(loan_nft_address, _LOAN_NFT_ABI)
        deal_id_bytes = self._normalize_deal_id(deal_id)
        return [int(tid) for tid in loan_nft.functions.getLoansForDeal(deal_id_bytes).call()]

    def get_deal_balance(self, loan_nft_address: str, deal_id: str) -> int:
        """
        Get total current balance for all loans in a deal.
        
        Parameters
        ----------
        loan_nft_address : str
            Address of the LoanNFT contract
        deal_id : str
            Deal identifier
        
        Returns
        -------
        int
            Total unpaid principal balance
        """
        loan_nft = self._get_contract(loan_nft_address, _LOAN_NFT_ABI)
        deal_id_bytes = self._normalize_deal_id(deal_id)
        return int(loan_nft.functions.getDealBalance(deal_id_bytes).call())

    def _send_tx(self, contract_fn: Any) -> str:
        tx = contract_fn.build_transaction(
            {
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
                "gas": settings.web3_default_gas,
                "gasPrice": self.w3.eth.gas_price,
            }
        )
        signed_tx = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        return tx_hash.hex()

    def _get_contract(self, address: str, abi: List[Dict[str, Any]]) -> Any:
        if not address:
            raise ValueError("Web3 contract address missing in settings.")
        return self.w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)

    def _normalize_deal_id(self, deal_id: str) -> bytes:
        if deal_id.startswith("0x") and len(deal_id) == 66:
            return bytes.fromhex(deal_id[2:])
        return Web3.keccak(text=deal_id)

    @staticmethod
    def _bytes32_to_hex(value: bytes) -> str:
        return "0x" + value.hex()


_TRANCHE_FACTORY_ABI: List[Dict[str, Any]] = [
    {
        "inputs": [],
        "name": "getAllDeals",
        "outputs": [{"type": "bytes32[]"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "dealId", "type": "bytes32"}],
        "name": "getDealInfo",
        "outputs": [{"type": "tuple"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "dealId", "type": "bytes32"}],
        "name": "getTranchesForDeal",
        "outputs": [{"type": "address[]"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "dealId", "type": "bytes32"},
            {"name": "name", "type": "string"},
            {"name": "arranger", "type": "address"},
            {"name": "closingDate", "type": "uint256"},
            {"name": "maturityDate", "type": "uint256"},
        ],
        "name": "registerDeal",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {
                "components": [
                    {"name": "dealId", "type": "bytes32"},
                    {"name": "trancheId", "type": "string"},
                    {"name": "name", "type": "string"},
                    {"name": "symbol", "type": "string"},
                    {"name": "originalFaceValue", "type": "uint256"},
                    {"name": "couponRateBps", "type": "uint256"},
                    {"name": "paymentFrequency", "type": "uint8"},
                    {"name": "maturityDate", "type": "uint256"},
                    {"name": "paymentToken", "type": "address"},
                    {"name": "transferValidator", "type": "address"},
                    {"name": "admin", "type": "address"},
                    {"name": "issuer", "type": "address"},
                    {"name": "trustee", "type": "address"},
                ],
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "deployTranche",
        "outputs": [{"type": "address"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


_TRANSFER_VALIDATOR_ABI: List[Dict[str, Any]] = [
    {
        "inputs": [
            {"name": "investor", "type": "address"},
            {"name": "verified", "type": "bool"},
            {"name": "expiry", "type": "uint256"},
        ],
        "name": "setKYCStatusWithExpiry",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "investor", "type": "address"},
            {"name": "accredited", "type": "bool"},
        ],
        "name": "setAccreditationStatus",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "investor", "type": "address"},
            {"name": "jurisdiction", "type": "bytes2"},
        ],
        "name": "setJurisdiction",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "investor", "type": "address"},
            {"name": "sanctioned", "type": "bool"},
        ],
        "name": "setSanctionsStatus",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "investor", "type": "address"},
            {"name": "lockupExpiry", "type": "uint256"},
        ],
        "name": "setLockup",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


_SERVICER_ORACLE_ABI: List[Dict[str, Any]] = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "dealId", "type": "bytes32"},
                    {"name": "periodNumber", "type": "uint256"},
                    {"name": "reportingDate", "type": "uint256"},
                    {"name": "submissionTimestamp", "type": "uint256"},
                    {"name": "scheduledPrincipal", "type": "uint256"},
                    {"name": "scheduledInterest", "type": "uint256"},
                    {"name": "actualPrincipal", "type": "uint256"},
                    {"name": "actualInterest", "type": "uint256"},
                    {"name": "prepayments", "type": "uint256"},
                    {"name": "curtailments", "type": "uint256"},
                    {"name": "defaults", "type": "uint256"},
                    {"name": "lossSeverity", "type": "uint256"},
                    {"name": "recoveries", "type": "uint256"},
                    {"name": "totalLoanCount", "type": "uint256"},
                    {"name": "currentLoanCount", "type": "uint256"},
                    {"name": "delinquentLoanCount", "type": "uint256"},
                    {"name": "totalUPB", "type": "uint256"},
                    {"name": "wac", "type": "uint256"},
                    {"name": "wam", "type": "uint256"},
                    {"name": "waLTV", "type": "uint256"},
                    {"name": "dataHash", "type": "bytes32"},
                    {"name": "zkProof", "type": "bytes"},
                    {"name": "isVerified", "type": "bool"},
                    {"name": "isDisputed", "type": "bool"},
                    {"name": "submitter", "type": "address"},
                ],
                "name": "data",
                "type": "tuple",
            }
        ],
        "name": "submitLoanTape",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


_WATERFALL_ENGINE_ABI: List[Dict[str, Any]] = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "dealId", "type": "bytes32"},
                    {"name": "paymentToken", "type": "address"},
                    {"name": "tranches", "type": "address[]"},
                    {"name": "seniorities", "type": "uint8[]"},
                    {"name": "interestRatesBps", "type": "uint256[]"},
                    {"name": "trusteeFeesBps", "type": "uint256"},
                    {"name": "servicerFeesBps", "type": "uint256"},
                    {"name": "trusteeAddress", "type": "address"},
                    {"name": "servicerAddress", "type": "address"},
                    {"name": "principalSequential", "type": "bool"},
                    {"name": "isActive", "type": "bool"},
                ],
                "name": "config",
                "type": "tuple",
            }
        ],
        "name": "configureWaterfall",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "dealId", "type": "bytes32"},
            {"name": "period", "type": "uint256"},
        ],
        "name": "executeWaterfall",
        "outputs": [{"type": "tuple"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


_LOAN_NFT_ABI: List[Dict[str, Any]] = [
    # Update single loan status
    {
        "inputs": [
            {"name": "tokenId", "type": "uint256"},
            {"name": "newStatus", "type": "uint8"},
            {"name": "newBalance", "type": "uint256"},
        ],
        "name": "updateLoanStatus",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # Batch update loan statuses
    {
        "inputs": [
            {"name": "tokenIds", "type": "uint256[]"},
            {"name": "statuses", "type": "uint8[]"},
            {"name": "balances", "type": "uint256[]"},
        ],
        "name": "updateLoanStatusBatch",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # Get loan metadata
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "getLoanMetadata",
        "outputs": [
            {
                "components": [
                    {"name": "dealId", "type": "bytes32"},
                    {"name": "loanId", "type": "string"},
                    {"name": "originalBalance", "type": "uint256"},
                    {"name": "currentBalance", "type": "uint256"},
                    {"name": "noteRate", "type": "uint256"},
                    {"name": "originationDate", "type": "uint256"},
                    {"name": "maturityDate", "type": "uint256"},
                    {"name": "status", "type": "uint8"},
                    {"name": "dataHash", "type": "bytes32"},
                    {"name": "lastUpdated", "type": "uint256"},
                ],
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    # Get all loans for a deal
    {
        "inputs": [{"name": "dealId", "type": "bytes32"}],
        "name": "getLoansForDeal",
        "outputs": [{"name": "", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function",
    },
    # Get total balance for a deal
    {
        "inputs": [{"name": "dealId", "type": "bytes32"}],
        "name": "getDealBalance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    # Get loan count by status
    {
        "inputs": [
            {"name": "dealId", "type": "bytes32"},
            {"name": "status", "type": "uint8"},
        ],
        "name": "getLoanCountByStatus",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


_client_instance: Optional[Web3Client] = None


def get_web3_client() -> Web3Client:
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    if not settings.web3_enabled:
        raise ValueError("Web3 integration is disabled (RMBS_WEB3_ENABLED=false).")

    addresses = Web3Addresses(
        tranche_factory=settings.web3_tranche_factory,
        transfer_validator=settings.web3_transfer_validator,
        servicer_oracle=settings.web3_servicer_oracle,
        waterfall_engine=settings.web3_waterfall_engine,
        loan_nft=getattr(settings, "web3_loan_nft", ""),
    )
    _client_instance = Web3Client(
        rpc_url=settings.web3_rpc_url,
        private_key=settings.web3_admin_private_key,
        addresses=addresses,
    )
    return _client_instance

