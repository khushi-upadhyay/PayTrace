# PayPal Sandbox Setup Guide

This guide describes how to configure PayTrace to connect to live PayPal Developer Sandbox accounts, create orders, process buyer approval, and receive verified webhooks.

## 1. Create a PayPal Developer Account & Sandbox App

1. Navigate to the [PayPal Developer Portal](https://developer.paypal.com/).
2. Log in and go to **Apps & Credentials** > **Sandbox**.
3. Click **Create App**:
   - **App Name**: `PayTrace Sandbox App`
   - **App Type**: `Merchant`
4. Copy your credentials:
   - **Client ID**
   - **Secret**

## 2. Configure Environment Variables

### Backend (`backend/.env`)
```dotenv
PAYPAL_CLIENT_ID=your_sandbox_client_id_here
PAYPAL_CLIENT_SECRET=your_sandbox_client_secret_here
PAYPAL_ENVIRONMENT=sandbox
PAYPAL_WEBHOOK_ID=your_webhook_id_here
```

### Frontend (`frontend/.env.local`)
```dotenv
NEXT_PUBLIC_PAYPAL_CLIENT_ID=your_sandbox_client_id_here
NEXT_PUBLIC_PAYPAL_ENVIRONMENT=sandbox
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## 3. Webhook Tunneling for Local Development

To receive real-time webhook events from PayPal on your local machine:

1. Launch a tunnel with `ngrok` or `localtunnel`:
   ```bash
   ngrok http 8000
   ```
2. Copy the public HTTPS forwarding URL (e.g., `https://abc-123.ngrok-free.app`).
3. In PayPal Developer Dashboard:
   - Open your Sandbox App.
   - Click **Add Webhook**.
   - **Webhook URL**: `https://abc-123.ngrok-free.app/api/webhooks/paypal`
   - Subscribe to the following events:
     - `CHECKOUT.ORDER.APPROVED`
     - `PAYMENT.CAPTURE.COMPLETED`
     - `PAYMENT.CAPTURE.DENIED`
     - `PAYMENT.CAPTURE.REFUNDED`
4. Copy the resulting **Webhook ID** into `PAYPAL_WEBHOOK_ID` in `backend/.env`.

## 4. Test Buyer Accounts

In PayPal Developer Portal under **Testing Tools** > **Sandbox Accounts**:
- Find or create a Personal test account (e.g., `sb-buyer@personal.example.com`).
- Use this account when completing checkout approvals in the PayPal popup.

## 5. Offline / Zero-Credential Mode

PayTrace is designed to run completely offline without PayPal credentials:
- When `PAYPAL_CLIENT_ID` or `PAYPAL_CLIENT_SECRET` are not set, PayTrace automatically activates its internal `MockPayPalSandbox`.
- Orders and captures are generated cleanly, and simulated webhooks can be replayed from the Demo Scenarios toolbar.
