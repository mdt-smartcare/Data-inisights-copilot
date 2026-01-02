# Frontend Quick Start Guide

## ✅ What's Been Setup

Your React frontend is now configured with:

### 1. **Folder Structure** ✓
```
src/
├── components/        # Reusable UI components
│   ├── chat/         # Chat-specific components
│   └── layout/       # Layout components
├── pages/            # Page components (Home, Chat, About)
├── services/         # API integration layer
├── hooks/            # Custom React hooks
├── types/            # TypeScript definitions
├── utils/            # Utility functions
└── config.ts         # App configuration
```

### 2. **Routing (React Router)** ✓
- Home page (`/`) - Landing page with app info
- Chat page (`/chat`) - Main chat interface
- About page (`/about`) - About the application
- 404 redirect to home

### 3. **CSS Library (Tailwind CSS)** ✓
- Tailwind CSS configured and ready
- Custom utility classes defined
- Responsive design utilities

### 4. **State Management** ✓
- TanStack Query for server state
- React hooks for local state

### 5. **API Integration** ✓
- Axios client configured
- Request/response interceptors
- Centralized error handling
- Environment-based configuration

### 6. **TypeScript** ✓
- Full type safety
- Interface definitions for API responses
- Type-safe routing

## 🚀 Next Steps to Start Development

### 1. Start the Development Server

```bash
cd frontend
npm run dev
```

The app will run at http://localhost:5173

### 2. Verify Backend Connection

Make sure your backend is running at http://localhost:8000. Update `.env` if using a different URL:

```env
VITE_API_BASE_URL=http://localhost:8000
```

### 3. Test the Application

1. Open http://localhost:5173
2. Click "Start Chatting"
3. Try sending a message (requires backend to be running)

## 📝 Common Development Tasks

### Adding a New Page

1. Create component in `src/pages/`:
```tsx
// src/pages/NewPage.tsx
export default function NewPage() {
  return <div>New Page Content</div>;
}
```

2. Add route in [src/App.tsx](src/App.tsx):
```tsx
import NewPage from './pages/NewPage';

// In Routes component
<Route path="/new" element={<NewPage />} />
```

### Creating a Reusable Component

```tsx
// src/components/Button.tsx
interface ButtonProps {
  onClick: () => void;
  children: React.ReactNode;
}

export default function Button({ onClick, children }: ButtonProps) {
  return (
    <button onClick={onClick} className="btn-primary">
      {children}
    </button>
  );
}
```

### Adding a New API Service

```tsx
// src/services/feedbackService.ts
import { apiClient } from './api';
import { API_ENDPOINTS } from '../config';

export const feedbackService = {
  submit: async (data: FeedbackRequest) => {
    const response = await apiClient.post(API_ENDPOINTS.FEEDBACK, data);
    return response.data;
  },
};
```

### Using TanStack Query for API Calls

```tsx
import { useQuery } from '@tanstack/react-query';
import { chatService } from '../services/chatService';

function MyComponent() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => chatService.getConversationHistory(conversationId),
  });

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {error.message}</div>;
  
  return <div>{/* Use data */}</div>;
}
```

## 🎨 Styling with Tailwind

### Common Patterns

**Layout:**
```tsx
<div className="flex flex-col items-center justify-center min-h-screen">
  <div className="max-w-4xl mx-auto px-6 py-8">
    {/* Content */}
  </div>
</div>
```

**Cards:**
```tsx
<div className="bg-white rounded-lg shadow-md p-6">
  {/* Card content */}
</div>
```

**Buttons:**
```tsx
<button className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-lg">
  Click Me
</button>
```

**Forms:**
```tsx
<input
  type="text"
  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
/>
```

## 🔧 Configuration Files

| File | Purpose |
|------|---------|
| `vite.config.ts` | Vite configuration |
| `tailwind.config.js` | Tailwind CSS configuration |
| `tsconfig.json` | TypeScript configuration |
| `.env` | Environment variables |
| `package.json` | Dependencies and scripts |

## 🐛 Troubleshooting

### Port Already in Use
```bash
# Change port in vite.config.ts
server: { port: 3000 }
```

### API Connection Failed
- Verify backend is running
- Check CORS settings on backend
- Verify `VITE_API_BASE_URL` in `.env`

### Tailwind Styles Not Working
```bash
# Rebuild the project
npm run build
npm run dev
```

## 📚 Additional Resources

- [React Documentation](https://react.dev)
- [Tailwind CSS Docs](https://tailwindcss.com/docs)
- [React Router Docs](https://reactrouter.com)
- [TanStack Query Docs](https://tanstack.com/query)
- [Vite Documentation](https://vite.dev)

## 🎯 Recommended Next Features

1. **Add shadcn/ui components** - Pre-built accessible components
2. **Implement authentication** - Login/register flow
3. **Add chat history sidebar** - View past conversations
4. **Dark mode** - Theme toggle
5. **Loading skeletons** - Better loading states
6. **Error boundaries** - Graceful error handling
7. **Unit tests** - Vitest + React Testing Library

Happy coding! 🚀
