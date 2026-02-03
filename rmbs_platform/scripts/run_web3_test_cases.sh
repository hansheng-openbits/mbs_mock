#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
ARRANGER_HEADER="X-User-Role: arranger"
SERVICER_HEADER="X-User-Role: servicer"

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env var: ${name}" >&2
    exit 1
  fi
}

require_env WEB3_ARRANGER_ADDRESS
require_env WEB3_ADMIN_ADDRESS
require_env WEB3_ISSUER_ADDRESS
require_env WEB3_TRUSTEE_ADDRESS
require_env WEB3_SERVICER_ADDRESS
require_env WEB3_TRANSFER_VALIDATOR
require_env WEB3_PAYMENT_TOKEN

curl_json() {
  local method="$1"
  local path="$2"
  local header="$3"
  local payload="${4:-}"
  if [[ -n "$payload" ]]; then
    curl -s -X "$method" "${BASE_URL}${path}" \
      -H "Content-Type: application/json" \
      -H "${header}" \
      -d "$payload"
  else
    curl -s -X "$method" "${BASE_URL}${path}" \
      -H "${header}"
  fi
}

echo "== Web3 Health =="
curl_json GET "/web3/health" "${ARRANGER_HEADER}" | jq .

echo "== Register PRIME_2024_1 =="
curl_json POST "/web3/deals" "${ARRANGER_HEADER}" "{
  \"deal_id\": \"PRIME_2024_1\",
  \"deal_name\": \"Prime Residential Trust 2024-1\",
  \"arranger\": \"${WEB3_ARRANGER_ADDRESS}\",
  \"closing_date\": 1706140800,
  \"maturity_date\": 2658873600
}" | jq .

echo "== Publish tranches from PRIME_2024_1 =="
curl_json POST "/web3/deals/PRIME_2024_1/tranches/publish" "${ARRANGER_HEADER}" "{
  \"payment_token\": \"${WEB3_PAYMENT_TOKEN}\",
  \"transfer_validator\": \"${WEB3_TRANSFER_VALIDATOR}\",
  \"admin\": \"${WEB3_ADMIN_ADDRESS}\",
  \"issuer\": \"${WEB3_ISSUER_ADDRESS}\",
  \"trustee\": \"${WEB3_TRUSTEE_ADDRESS}\",
  \"payment_frequency\": 1
}" | jq .

echo "== Register tranche addresses (manual) =="
echo "Set WEB3_TRANCHE_ADDRESSES as JSON array to register."
if [[ -n "${WEB3_TRANCHE_ADDRESSES:-}" ]]; then
  curl_json POST "/web3/deals/PRIME_2024_1/tranches/register" "${ARRANGER_HEADER}" "{
    \"tranches\": ${WEB3_TRANCHE_ADDRESSES}
  }" | jq .
else
  echo "Skipping tranche registry update."
fi

echo "== Publish waterfall for PRIME_2024_1 =="
if [[ -n "${WEB3_TRANCHE_ADDRESSES:-}" ]]; then
  curl_json POST "/web3/waterfall/publish/PRIME_2024_1" "${ARRANGER_HEADER}" "{
    \"payment_token\": \"${WEB3_PAYMENT_TOKEN}\",
    \"tranches\": ${WEB3_TRANCHE_ADDRESSES},
    \"trustee_address\": \"${WEB3_TRUSTEE_ADDRESS}\",
    \"servicer_address\": \"${WEB3_SERVICER_ADDRESS}\",
    \"trustee_fees_bps\": 10,
    \"servicer_fees_bps\": 25,
    \"principal_sequential\": true
  }" | jq .
else
  echo "Skipping waterfall publish (no tranche addresses)."
fi

echo "== Oracle publish period 1 (PRIME_2024_1) =="
curl_json POST "/web3/oracle/publish/PRIME_2024_1/1" "${SERVICER_HEADER}" | jq .

echo "== Oracle publish range (NONQM_2023_1) =="
curl_json POST "/web3/oracle/publish/NONQM_2023_1" "${SERVICER_HEADER}" "{
  \"start_period\": 1,
  \"end_period\": 3
}" | jq .

echo "== Full publish workflow (SAMPLE_RMBS_2024) =="
curl_json POST "/web3/deals/SAMPLE_RMBS_2024/publish" "${ARRANGER_HEADER}" "{
  \"deal_name\": \"Freddie Mac Sample 2017-2020\",
  \"arranger\": \"${WEB3_ARRANGER_ADDRESS}\",
  \"closing_date\": 1706572800,
  \"maturity_date\": 2656867200,
  \"payment_token\": \"${WEB3_PAYMENT_TOKEN}\",
  \"transfer_validator\": \"${WEB3_TRANSFER_VALIDATOR}\",
  \"admin\": \"${WEB3_ADMIN_ADDRESS}\",
  \"issuer\": \"${WEB3_ISSUER_ADDRESS}\",
  \"trustee\": \"${WEB3_TRUSTEE_ADDRESS}\",
  \"trustee_address\": \"${WEB3_TRUSTEE_ADDRESS}\",
  \"servicer_address\": \"${WEB3_SERVICER_ADDRESS}\"
}" | jq .

echo "== Negative test (INVALID) =="
curl_json POST "/web3/deals/INVALID/tranches/publish" "${ARRANGER_HEADER}" "{
  \"payment_token\": \"${WEB3_PAYMENT_TOKEN}\",
  \"transfer_validator\": \"${WEB3_TRANSFER_VALIDATOR}\",
  \"admin\": \"${WEB3_ADMIN_ADDRESS}\",
  \"issuer\": \"${WEB3_ISSUER_ADDRESS}\",
  \"trustee\": \"${WEB3_TRUSTEE_ADDRESS}\",
  \"payment_frequency\": 1
}" | jq .
