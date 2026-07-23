export type UserRole = 'buyer' | 'seller' | 'both'

export interface RegisterRequest {
  phone: string
  nickname: string
  role: UserRole
}

export interface RegisterSuccessData {
  user_id: string
  role: UserRole
  status: 'active'
  created_at: string
  phone_masked?: string
}

export interface ApiEnvelope<T> {
  code: string
  message: string
  data: T | null
  request_id: string
  timestamp: string
}

export interface FieldErrors {
  errors?: Record<string, string[]>
}
