// Chat Types
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  sources?: Source[];
  sqlQuery?: string;
  suggestedQuestions?: string[];
  chartData?: ChartData;
  traceId?: string;
  processingTime?: number;
}

export interface ChartData {
  type: 'line' | 'bar' | 'pie' | 'area';
  title?: string;
  data: any[];
  xKey?: string;
  yKey?: string;
  colors?: string[];
}

export interface Source {
  id?: string;
  content: string;
  metadata?: Record<string, any>;
  score?: number;
}

export interface ChatRequest {
  query: string;
  conversation_id?: string;
}

export interface ChatResponse {
  answer: string;
  sources?: Source[];
  sql_query?: string;
  suggested_questions?: string[];
  chart_data?: ChartData;
  conversation_id: string;
  timestamp: string;
  trace_id?: string;
  processing_time?: number;
}

// Feedback Types
export interface FeedbackRequest {
  conversation_id: string;
  message_id: string;
  rating: number;
  comment?: string;
}

// Auth Types
export interface User {
  id: string;
  email: string;
  name?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name?: string;
}

export interface AuthResponse {
  user: User;
  token: string;
}
