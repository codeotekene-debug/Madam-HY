import requests
import uuid
import getpass
import json

# Moniepoint API endpoint
BASE_URL = "https://api.pos.moniepoint.com"

print("=" * 50)
print("       MONIEPOINT POS CONNECTION TEST")
print("=" * 50)

# Enter credentials securely
API_KEY ='REPLACE_WITH_MONIEPOINT_API_KEY'

# Client ID is optional for direct API-key authentication.
CLIENT_ID ='api-client-4985052-a51d040e-96c6-4050-9c32-ecaf412a1597'

TERMINAL_SERIAL ='C5BP008D071N7207'

# Enter payment details
try:
    amount = int(input("Enter payment amount: "))
except ValueError:
    print("Invalid amount!")
    exit()

# Generate unique merchant reference
merchant_reference = "HYTEST-" + uuid.uuid4().hex[:12].upper()

# API headers
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

# Payment payload
payload = {
    "terminalSerial": TERMINAL_SERIAL,
    "amount": amount,
    "merchantReference": merchant_reference,
    "transactionType": "PURCHASE",
    "paymentMethod": "ANY"
}

print("\nSending payment request to Moniepoint...")
print("Merchant Reference:", merchant_reference)

try:
    response = requests.post(
        f"{BASE_URL}/v1/transactions",
        headers=headers,
        json=payload,
        timeout=30
    )

    print("\nHTTP STATUS:", response.status_code)

    try:
        result = response.json()
        print("\nMONIEPOINT RESPONSE:")
        print(json.dumps(result, indent=4))
    except ValueError:
        print(response.text)

    if response.status_code == 202:
        print("\nSUCCESS!")
        print("Payment request accepted.")
        print("Check your Moniepoint POS terminal.")

    elif response.status_code == 401:
        print("\nAUTHENTICATION FAILED!")
        print("Check your API key and environment.")

    elif response.status_code == 400:
        print("\nINVALID REQUEST!")
        print("Check your terminal serial number and payment details.")

    else:
        print("\nREQUEST FAILED!")
        print("Check the response above.")

except requests.exceptions.Timeout:
    print("\nConnection timed out.")

except requests.exceptions.ConnectionError:
    print("\nUnable to connect to Moniepoint.")

except requests.exceptions.RequestException as error:
    print("\nERROR:", error)