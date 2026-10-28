# Architecture

## Surfaces

```mermaid
flowchart TB
    glasses[Meta glasses] --> android[Android app]
    web[Web app] --> api[Shared FastAPI backend]
    android --> api
    api --> models[Meta AI models]
    web --> fb[Facebook Marketplace]
    android --> fb
```

The web app and the Android app are thin clients of one backend. Marketplace is reached by
handoff: the app copies an approved draft and opens the create-item page; nothing is posted on
anyone's behalf. The glasses reach the backend through the Android app.

## Inside the backend

```mermaid
flowchart TB
    subgraph browser
        UI[React app]
    end
    subgraph backend[FastAPI service]
        API[/HTTP API/]
        AG[Agent loop]
        PR[Profiles]
        MT[Matcher]
        CL[Model API client]
        CH[Channels: web, WhatsApp, Messenger, catalog]
    end
    UI --> API
    API --> AG
    AG --> PR
    AG --> MT
    AG --> CL
    CL --> META[(Meta Model API)]
    CL --> OW[(Open-weight providers)]
    CH --> API
```

- The **backend** owns everything that reasons: the agent loop, the profiles, the matcher and
  the single Model API client.
- The **frontend** renders evidence and lets people edit it. It has no model logic.
- **Channels** are thin adapters that turn a WhatsApp message, a Messenger message or a catalog
  export into the same API calls the web app makes.

Request flow and the agent loop get their own diagrams as those parts land.
