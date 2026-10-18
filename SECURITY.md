# Security notes

## Intended use

AudioLink Secure is a learning prototype for live audio sharing between devices whose users have explicitly authorized the session. It is not a covert monitoring tool.

## Current MVP limitations

- Session and receiver approval state are held in process memory and are lost on restart.
- A pairing code is a temporary bearer secret. Share it only with the intended receiver.
- The signaling service has basic per-IP rate limits, but is not yet hardened for production.
- The WebRTC configuration currently uses a public STUN server only. Some NATs and firewalls require a TURN relay; cross-network connectivity is not guaranteed until TURN is configured.
- There is no durable account system, trusted-device reconnect, persistent revocation store, or production audit log.
- Do not store audio or pairing codes in public logs.

## Safe deployment checklist

Before public/production use:
1. Keep the repository private until the security review is complete.
2. Deploy only over HTTPS/WSS.
3. Add durable authenticated accounts and short-lived, revocable device credentials.
4. Configure a TURN provider using short-lived credentials; do not commit relay secrets.
5. Add distributed rate limiting, session limits, expiry, and security tests.
6. Verify that Stop sharing releases all capture tracks and closes peer connections.
7. Keep a visible capture indicator and require explicit user action for each new audio-sharing session.

## Reporting

Please report security issues privately to the repository owner rather than posting exploit details in a public issue.
