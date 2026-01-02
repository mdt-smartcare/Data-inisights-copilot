# Chat Components Documentation

This directory contains modular, reusable components for the chat interface.

## Components Overview

### 1. **ChatHeader**
Header component for the chat page with optional back button.

**Props:**
- `title?: string` - Header title (default: "FHIR RAG Chat")
- `showBackButton?: boolean` - Show back navigation button (default: false)

**Usage:**
```tsx
import { ChatHeader } from '../components/chat';

<ChatHeader title="My Chat" showBackButton />
```

---

### 2. **ChatMessage**
Individual message bubble component with support for user/assistant messages and sources.

**Props:**
- `message: Message` - Message object containing id, role, content, timestamp, and sources

**Features:**
- Different styling for user vs assistant messages
- Displays timestamp
- Shows AI avatar for assistant messages
- Renders source citations if available

**Usage:**
```tsx
import { ChatMessage } from '../components/chat';

<ChatMessage message={messageObject} />
```

---

### 3. **MessageList**
Container component for displaying all messages with auto-scroll functionality.

**Props:**
- `messages: Message[]` - Array of message objects
- `isLoading?: boolean` - Show loading indicator (default: false)
- `emptyStateProps?: object` - Props to pass to EmptyState component

**Features:**
- Auto-scrolls to bottom when new messages arrive
- Shows empty state when no messages
- Displays loading indicator when waiting for response

**Usage:**
```tsx
import { MessageList } from '../components/chat';

<MessageList 
  messages={messages}
  isLoading={isPending}
  emptyStateProps={{
    title: 'Welcome!',
    suggestions: ['Question 1', 'Question 2']
  }}
/>
```

---

### 4. **ChatInput**
Input component with send button and character counter.

**Props:**
- `onSendMessage: (message: string) => void` - Callback when message is sent
- `isDisabled?: boolean` - Disable input (default: false)
- `placeholder?: string` - Input placeholder (default: "Type your message...")
- `maxLength?: number` - Maximum character limit (default: 2000)

**Features:**
- Auto-expanding textarea
- Enter to send, Shift+Enter for new line
- Character counter with limit indicator
- Send button with icon
- Keyboard shortcuts

**Usage:**
```tsx
import { ChatInput } from '../components/chat';

<ChatInput 
  onSendMessage={handleSend}
  isDisabled={isLoading}
  maxLength={2000}
/>
```

---

### 5. **EmptyState**
Welcome screen shown when there are no messages.

**Props:**
- `title?: string` - Main title text
- `subtitle?: string` - Subtitle text
- `suggestions?: string[]` - Array of suggested questions

**Features:**
- Attractive icon
- Customizable text
- Clickable suggestion cards (styled only, click handler needs to be added)

**Usage:**
```tsx
import { EmptyState } from '../components/chat';

<EmptyState 
  title="Start chatting!"
  suggestions={['Ask about...', 'Learn about...']}
/>
```

---

### 6. **LoadingIndicator**
Animated loading indicator for when the assistant is thinking.

**Props:**
- `text?: string` - Loading text (default: "Thinking...")

**Features:**
- Animated bouncing dots
- Customizable loading text

**Usage:**
```tsx
import { LoadingIndicator } from '../components/chat';

<LoadingIndicator text="Processing..." />
```

---

### 7. **SourceList**
Displays source citations for assistant responses.

**Props:**
- `sources: Source[]` - Array of source objects

**Features:**
- Numbered citations
- Truncated content preview
- Score display if available
- Styled cards for readability

**Usage:**
```tsx
import { SourceList } from '../components/chat';

<SourceList sources={message.sources} />
```

---

## Component Composition

The components are designed to work together but can also be used independently:

```tsx
// Full chat page example
import { ChatHeader, MessageList, ChatInput } from '../components/chat';

function ChatPage() {
  return (
    <div className="flex flex-col h-screen">
      <ChatHeader title="My Chat" showBackButton />
      <MessageList messages={messages} isLoading={isLoading} />
      <ChatInput onSendMessage={handleSend} />
    </div>
  );
}
```

## Customization

All components use Tailwind CSS classes and can be easily customized:

1. **Colors**: Modify the color classes (e.g., `bg-blue-600` → `bg-purple-600`)
2. **Sizing**: Adjust padding, margins, and dimensions
3. **Layout**: Components are flexible and responsive by default

## Type Definitions

Components use types from `src/types/index.ts`:

```typescript
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  sources?: Source[];
}

interface Source {
  id: string;
  content: string;
  metadata?: Record<string, any>;
  score?: number;
}
```

## Best Practices

1. **Keep components focused**: Each component has a single responsibility
2. **Use composition**: Combine components to build complex UIs
3. **Pass data down**: Use props to customize behavior
4. **Handle events up**: Use callbacks for user interactions
5. **Maintain accessibility**: Components include ARIA labels where appropriate

## Future Enhancements

Potential improvements for these components:

- [ ] Add click handlers to EmptyState suggestions
- [ ] Add copy button to ChatMessage
- [ ] Add message editing functionality
- [ ] Add message deletion
- [ ] Add reactions/feedback buttons
- [ ] Add file upload support to ChatInput
- [ ] Add voice input option
- [ ] Add markdown rendering in messages
- [ ] Add code syntax highlighting
- [ ] Add image support in messages
