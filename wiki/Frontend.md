# Frontend Guide

This page details the architecture and development guidelines for the frontend of Data Insights Copilot.

## Architecture

The frontend is a **Single Page Application (SPA)** built with:
- **Framework**: React 19 + TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS 4
- **State Management**: React Query (server state), Context API (client state)
- **Routing**: React Router 7
- **Visualization**: Recharts
- **HTTP Client**: Axios
- **Markdown**: React Markdown

## Dependencies

Key libraries used in the project:
| Library | Purpose |
|---------|---------|
| `@tanstack/react-query` | Server state management, caching, and optimistic updates. |
| `react-router-dom` | Client-side routing. |
| `react-toastify` | Notification system. |
| `recharts` | Data visualization charts. |
| `axios` | HTTP requests to the backend. |


## Directory Structure

- `src/components`: Reusable UI components.
    - `ChatPage`: Main chat interface.
    - `ConfigPage`: Configuration management.
    - `ConnectionManager`: Database connection handling.
- `src/pages`: Top-level route components.
- `src/contexts`: Global state providers (`AuthContext`, `ToastProvider`).
- `src/hooks`: Custom React hooks.
- `src/types`: TypeScript interfaces.

## Key Components

### Chat Interface (`src/pages/ChatPage.tsx`)
The primary user interaction point.
- **Features**: 
    - Real-time chat history.
    - Dynamic chart rendering using `Recharts`.
    - Markdown rendering for text responses.

### Configuration (`src/pages/ConfigPage.tsx`)
Admin panel for managing system behavior and agent context.
- **Features**:
    - Database connection management (`database` sources).
    - Multi-modal file uploads (`file` sources) for document extraction.
    - System prompt versioning and tailored AI prompt generation.
    - Embedding job monitoring.

## State Management

We use **TanStack Query (React Query)** for all server-side data fetching.
- **Caching**: Automatic caching and revalidation.
- **Mutations**: Optimistic updates for responsive UI.

**Context API** handles:
- **Authentication**: User session and token storage.
- **Notifications**: Toast messages for errors/success.

## Development Workflow

1.  **Start Dev Server**:
    ```bash
    npm run dev
    ```

2.  **Lint & Format**:
    ```bash
    npm run lint
    ```

3.  **Build for Production**:
    ```bash
    npm run build
    ```
