# OpenID Connect login

The authorization code flow in OAuth 2.0 ([RFC 6749 Section 4.1](https://www.rfc-editor.org/rfc/rfc6749#section-4.1), Figure 3) with the steps OpenID Connect adds to it ([OpenID Connect Core 1.0 Section 3.1.1](https://openid.net/specs/openid-connect-core-1_0.html#CodeFlowSteps)). Redrawn from those two texts.

The browser carries the code and never sees a token. The client trades the code for tokens on a direct call that the user can't tamper with. The implicit and hybrid flows are not drawn.

```mermaid
---
config:
  theme: base
  fontFamily: Inter, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif
  themeVariables:
    fontSize: 15px
    lineColor: "#64748B"
    primaryTextColor: "#0F172A"
    actorBkg: "#FFFFFF"
    actorBorder: "#94A3B8"
    actorTextColor: "#0F172A"
    actorLineColor: "#64748B"
    signalColor: "#64748B"
    signalTextColor: "#0F172A"
    noteBkgColor: "#FFFFFF"
    noteBorderColor: "#94A3B8"
    noteTextColor: "#0F172A"
  themeCSS: >-
    .messageText{paint-order:stroke;stroke:#FFFFFF;stroke-width:3px;stroke-linejoin:round}
---
sequenceDiagram
    accTitle: L4 Detail -- OpenID Connect authorization code login
    accDescr: The client redirects the user's browser to the authorization server. The user signs in and consents, and the server redirects the browser back to the client with an authorization code. The client sends the code to the token endpoint and receives an ID token and an access token, then validates the ID token.
    participant user as User
    participant browser as Browser
    participant client as Client
    participant auth as Authorization server
    client->>browser: Redirect to the authorization endpoint
    browser->>auth: Authentication request
    auth->>user: Ask to sign in and consent
    user->>auth: Credentials and consent
    auth->>browser: Redirect to the client with a code
    browser->>client: Code and state
    client->>auth: Token request with the code
    auth->>client: ID token and access token
    Note over client: Validates the ID token
```

*Figure 1. L4 Detail -- OpenID Connect authorization code login.* Up: [Worked examples](../README.md).
