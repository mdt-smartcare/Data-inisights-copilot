# Data Insights Copilot Frontend

A modern React + TypeScript frontend for the Data Insights Copilot application.

## 🚀 Tech Stack

- **React 19** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **Tailwind CSS** - Styling
- **React Router** - Client-side routing
- **TanStack Query** - Server state management
- **Axios** - HTTP client

## 📁 Project Structure

```
src/
├── components/        # Reusable UI components
│   ├── chat/         # Chat-specific components
│   └── layout/       # Layout components (Header, Footer, etc.)
├── pages/            # Page components
│   ├── HomePage.tsx
│   ├── ChatPage.tsx
│   └── AboutPage.tsx
├── services/         # API services
│   ├── api.ts        # Axios instance and interceptors
│   └── chatService.ts
├── hooks/            # Custom React hooks
├── types/            # TypeScript type definitions
├── utils/            # Utility functions
├── config.ts         # App configuration
├── App.tsx           # Main app component with routing
└── main.tsx          # App entry point
```

## 🛠️ Development Setup

### Prerequisites

- Node.js 18+ and npm/yarn/pnpm
- Backend API running on http://localhost:8000

### Installation

1. Install dependencies:
```bash
npm install
```

2. Create environment file:
```bash
cp .env.example .env
```

3. Update `.env` with your backend API URL:
```env
VITE_API_BASE_URL=http://localhost:8000
```

### Run Development Server

```bash
npm run dev
```

The app will be available at http://localhost:5173

### Build for Production

```bash
npm run build
```

### Preview Production Build

```bash
npm run preview
```

## 🎨 Styling

This project uses **Tailwind CSS** for styling. Custom utility classes are defined in `src/index.css`.

### Custom Classes

- `.btn-primary` - Primary button style
- `.btn-secondary` - Secondary button style

## 🔌 API Integration

API calls are handled through services in the `src/services` directory:

- **api.ts**: Base axios configuration with interceptors
- **chatService.ts**: Chat-related API calls

Example usage:
```typescript
import { chatService } from './services/chatService';

const response = await chatService.sendMessage({
  query: 'What is FHIR?',
  conversation_id: 'optional-id'
});
```

## 🧪 Testing

```bash
npm run lint
```

## 📝 Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint

## 🔐 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_BASE_URL` | Backend API base URL | `http://localhost:8000` |

## 🚧 Next Steps

### Recommended Enhancements

1. **Authentication**
   - Implement login/register pages
   - Add protected routes
   - Token management

2. **UI Components**
   - Add a component library (shadcn/ui or MUI)
   - Create reusable chat components
   - Add loading states and error boundaries

3. **Features**
   - Conversation history sidebar
   - Export chat functionality
   - Dark mode support
   - Feedback mechanism

4. **Testing**
   - Add Vitest for unit tests
   - Add React Testing Library
   - E2E tests with Playwright

5. **Performance**
   - Code splitting
   - Lazy loading routes
   - Optimize bundle size

